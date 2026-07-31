"""Database access for the single-row local license activation cache."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.db.models import LicenseStateRow

_INSERT_BY_DIALECT = {"postgresql": pg_insert, "sqlite": sqlite_insert}
_ROW_ID = 1


def _as_utc(value: datetime) -> datetime:
    # SQLite drops tzinfo on round-trip even with DateTime(timezone=True);
    # every value this repository ever writes is UTC, so a naive read is UTC.
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class StoredLicenseState:
    license_key: str
    hwid: str
    tier: str
    expires_at: datetime
    last_validated_at: datetime
    signature: str = ""


class LicenseStateRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def save(self, state: StoredLicenseState) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                dialect_name = session.bind.dialect.name
                insert_fn = _INSERT_BY_DIALECT.get(dialect_name, sqlite_insert)
                values = {
                    "license_key": state.license_key,
                    "hwid": state.hwid,
                    "tier": state.tier,
                    "expires_at": state.expires_at,
                    "last_validated_at": state.last_validated_at,
                    "signature": state.signature,
                }
                stmt = insert_fn(LicenseStateRow).values(id=_ROW_ID, **values)
                stmt = stmt.on_conflict_do_update(index_elements=["id"], set_=values)
                await session.execute(stmt)

    async def load(self) -> Optional[StoredLicenseState]:
        async with self._session_factory() as session:
            row = (
                await session.execute(select(LicenseStateRow).where(LicenseStateRow.id == _ROW_ID))
            ).scalar_one_or_none()
        if row is None:
            return None
        return StoredLicenseState(
            license_key=row.license_key,
            hwid=row.hwid,
            tier=row.tier,
            expires_at=_as_utc(row.expires_at),
            last_validated_at=_as_utc(row.last_validated_at),
            signature=row.signature,
        )


async def ensure_license_state_table(session_factory: async_sessionmaker) -> None:
    engine = session_factory.kw["bind"]
    async with engine.begin() as connection:
        await connection.run_sync(LicenseStateRow.__table__.create, checkfirst=True)
