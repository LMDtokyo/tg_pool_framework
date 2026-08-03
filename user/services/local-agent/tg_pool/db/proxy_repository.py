"""Database access for the reusable proxy inventory."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from tg_pool.db.models import ProxyRow
from tg_pool.proxy.proxy_checker import ProxyState


_INSERT_BY_DIALECT = {"postgresql": pg_insert, "sqlite": sqlite_insert}


@dataclass(frozen=True)
class StoredProxy:
    id: int
    proxy_type: str
    host: str
    port: int
    username: str
    password: str
    version: str
    status: str
    response_ms: Optional[float]
    country: Optional[str]
    error_message: Optional[str]
    last_checked_at: Optional[datetime]
    ban_signal_count: int
    last_ban_signal_at: Optional[datetime]

    def checker_config(self, timeout: float) -> Dict[str, Any]:
        return {
            "type": self.proxy_type,
            "host": self.host,
            "port": self.port,
            "username": self.username or None,
            "password": self.password or None,
            "timeout": timeout,
        }


class ProxyRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def list_all(self) -> List[StoredProxy]:
        async with self._session_factory() as session:
            result = await session.execute(select(ProxyRow).order_by(ProxyRow.id))
            return [self._to_stored(row) for row in result.scalars().all()]

    async def list_for_check(
        self, proxy_ids: Optional[Sequence[int]] = None
    ) -> List[StoredProxy]:
        stmt = select(ProxyRow).order_by(ProxyRow.id)
        if proxy_ids is not None:
            stmt = stmt.where(ProxyRow.id.in_(proxy_ids))
        async with self._session_factory() as session:
            result = await session.execute(stmt)
            return [self._to_stored(row) for row in result.scalars().all()]

    async def upsert_many(self, proxies: Sequence[Dict[str, Any]]) -> int:
        async with self._session_factory() as session:
            async with session.begin():
                dialect_name = session.bind.dialect.name
                insert_fn = _INSERT_BY_DIALECT.get(dialect_name, sqlite_insert)
                for proxy in proxies:
                    stmt = insert_fn(ProxyRow).values(**proxy)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["proxy_type", "host", "port", "username"],
                        set_={
                            "password": proxy["password"],
                            "status": "unknown",
                            "response_ms": None,
                            "country": None,
                            "error_message": None,
                            "last_checked_at": None,
                            "updated_at": func.now(),
                        },
                    )
                    await session.execute(stmt)
        return len(proxies)

    async def delete_one(self, proxy_id: int) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    delete(ProxyRow).where(ProxyRow.id == proxy_id)
                )
                return bool(result.rowcount)

    async def delete_all(self) -> int:
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(delete(ProxyRow))
                return int(result.rowcount or 0)

    async def delete_bad(self) -> int:
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(delete(ProxyRow).where(ProxyRow.status == "bad"))
                return int(result.rowcount or 0)

    async def update_results(
        self, proxies: Sequence[StoredProxy], results: Sequence[ProxyState]
    ) -> None:
        checked_at = datetime.now(timezone.utc)
        async with self._session_factory() as session:
            async with session.begin():
                for proxy, state in zip(proxies, results):
                    row = await session.get(ProxyRow, proxy.id)
                    if row is None:
                        continue
                    row.status = "ok" if state.is_active else "bad"
                    row.response_ms = state.latency_ms
                    row.country = state.country
                    row.error_message = state.error_message
                    row.last_checked_at = checked_at

    async def record_ban_signal(
        self, *, proxy_type: str, host: str, port: int, username: str = ""
    ) -> bool:
        """
        Bumps the ban-signal counter for the stored proxy matching these exact
        connection details, if one exists. Returns False (no-op) for accounts
        running proxy-less or through a proxy that was never saved to this
        inventory (e.g. loaded straight from .env).
        """
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(ProxyRow).where(
                        ProxyRow.proxy_type == proxy_type,
                        ProxyRow.host == host,
                        ProxyRow.port == port,
                        ProxyRow.username == username,
                    )
                )
                row = result.scalar_one_or_none()
                if row is None:
                    return False
                row.ban_signal_count += 1
                row.last_ban_signal_at = datetime.now(timezone.utc)
                return True

    @staticmethod
    def _to_stored(row: ProxyRow) -> StoredProxy:
        return StoredProxy(
            id=row.id,
            proxy_type=row.proxy_type,
            host=row.host,
            port=row.port,
            username=row.username,
            password=row.password,
            version=row.version,
            status=row.status,
            response_ms=row.response_ms,
            country=row.country,
            error_message=row.error_message,
            last_checked_at=row.last_checked_at,
            ban_signal_count=row.ban_signal_count,
            last_ban_signal_at=row.last_ban_signal_at,
        )


async def ensure_proxy_table(session_factory: async_sessionmaker) -> None:
    """Create the dedicated local proxy table when it does not exist yet."""
    engine = session_factory.kw["bind"]
    async with engine.begin() as connection:
        await connection.run_sync(ProxyRow.__table__.create, checkfirst=True)
