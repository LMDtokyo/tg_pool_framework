"""
src/db/repository.py — AccountRepository: the only place ORM details are visible.

AccountRegistry depends on this interface, not on SQLAlchemy directly
(repository pattern — see architecture skill). Callers pass/receive
RegistryEntry objects; upsert()/load_all() do the ORM <-> dataclass mapping.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.config import AccountConfig, ProxyConfig
from src.db.models import AccountRow
from src.accounts.health_checker import AccountState, AccountStatus

if TYPE_CHECKING:
    from src.accounts.account_registry import RegistryEntry

logger = logging.getLogger(__name__)

_INSERT_BY_DIALECT = {"postgresql": pg_insert, "sqlite": sqlite_insert}


class AccountRepository:
    """Durable store for account config + health state, backed by Postgres."""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def upsert(self, entry: "RegistryEntry") -> None:
        """
        Atomically insert-or-update the row for entry.account.phone.

        Uses a dialect-specific INSERT ... ON CONFLICT DO UPDATE so concurrent
        upserts for the same phone (e.g. register() and update_state() firing
        their fire-and-forget writes back-to-back) never race on a
        select-then-insert check — the database itself serialises the write.
        """
        values = self._row_values(entry)
        async with self._session_factory() as session:
            async with session.begin():
                dialect_name = session.bind.dialect.name
                insert_fn = _INSERT_BY_DIALECT.get(dialect_name, sqlite_insert)
                stmt = insert_fn(AccountRow).values(phone=entry.account.phone, **values)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["phone"],
                    set_={**values, "updated_at": func.now()},
                )
                await session.execute(stmt)

    async def load_all(self) -> List["RegistryEntry"]:
        """Reconstruct all RegistryEntry rows from the accounts table."""
        from src.accounts.account_registry import RegistryEntry  # local import: avoid circular import

        async with self._session_factory() as session:
            result = await session.execute(select(AccountRow))
            rows = result.scalars().all()

        return [self._to_entry(row, RegistryEntry) for row in rows]

    # ------------------------------------------------------------------
    # Mapping helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_values(entry: "RegistryEntry") -> Dict[str, Any]:
        account = entry.account
        values: Dict[str, Any] = {
            "api_id": account.api_id,
            "api_hash": account.api_hash,
            "device_model": account.device_model,
            "system_version": account.system_version,
            "app_version": account.app_version,
            "session_dir": account.session_dir,
            "proxy_host": account.proxy.host if account.proxy else None,
            "proxy_port": account.proxy.port if account.proxy else None,
            "proxy_username": account.proxy.username if account.proxy else None,
            "proxy_password": account.proxy.password if account.proxy else None,
            "proxy_type": account.proxy.proxy_type if account.proxy else "socks5",
            "last_checked": entry.last_checked or datetime.now(timezone.utc),
            "role": entry.role,
            "folder": entry.folder,
        }

        state = entry.state
        if state is not None:
            values.update(
                status=state.status.value,
                is_premium=state.is_premium,
                restriction_expires=state.restriction_expires,
                error_message=state.error_message,
                username=state.username,
                first_name=state.first_name,
                country=state.country,
                has_2fa=state.has_2fa,
            )

        return values

    @staticmethod
    def _to_entry(row: AccountRow, registry_entry_cls) -> "RegistryEntry":
        proxy = None
        if row.proxy_host is not None and row.proxy_port is not None:
            proxy = ProxyConfig(
                host=row.proxy_host,
                port=row.proxy_port,
                username=row.proxy_username,
                password=row.proxy_password,
                proxy_type=row.proxy_type,
            )

        account = AccountConfig(
            api_id=row.api_id,
            api_hash=row.api_hash,
            phone=row.phone,
            proxy=proxy,
            device_model=row.device_model,
            system_version=row.system_version,
            app_version=row.app_version,
            session_dir=row.session_dir,
        )

        state = AccountState(
            status=AccountStatus(row.status),
            is_premium=row.is_premium,
            restriction_expires=row.restriction_expires,
            error_message=row.error_message,
            username=row.username,
            first_name=row.first_name,
            country=row.country,
            has_2fa=row.has_2fa,
        )

        return registry_entry_cls(
            account=account, state=state, last_checked=row.last_checked, first_seen=row.created_at,
            role=row.role, folder=row.folder,
        )


async def ensure_durable_tables(session_factory: async_sessionmaker) -> None:
    """Create local durable-store tables when they do not exist yet."""
    engine = session_factory.kw["bind"]
    async with engine.begin() as connection:
        for table in (AccountRow.__table__,):
            await connection.run_sync(table.create, checkfirst=True)
