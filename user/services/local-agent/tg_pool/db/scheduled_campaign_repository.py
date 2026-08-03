"""Database access for persisted, restart-durable scheduled campaigns."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from tg_pool.db.models import ScheduledCampaignRow


def _as_utc(value: datetime) -> datetime:
    # SQLite drops tzinfo on round-trip even with DateTime(timezone=True);
    # every value this repository ever writes is UTC, so a naive read is UTC.
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _as_utc_optional(value: Optional[datetime]) -> Optional[datetime]:
    return _as_utc(value) if value is not None else None


@dataclass(frozen=True)
class StoredScheduledCampaign:
    id: int
    name: str
    campaign_type: str
    payload: Dict[str, Any]
    start_at: datetime
    repeat_interval_hours: Optional[float]
    max_occurrences: Optional[int]
    enabled: bool
    occurrences_run: int
    next_run_at: datetime
    last_run_at: Optional[datetime]
    last_job_id: Optional[str]
    last_error: Optional[str]


class ScheduledCampaignRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def create(
        self,
        *,
        name: str,
        campaign_type: str,
        payload: Dict[str, Any],
        start_at: datetime,
        repeat_interval_hours: Optional[float],
        max_occurrences: Optional[int],
    ) -> StoredScheduledCampaign:
        async with self._session_factory() as session:
            async with session.begin():
                row = ScheduledCampaignRow(
                    name=name,
                    campaign_type=campaign_type,
                    payload=payload,
                    start_at=start_at,
                    repeat_interval_hours=repeat_interval_hours,
                    max_occurrences=max_occurrences,
                    enabled=True,
                    occurrences_run=0,
                    next_run_at=start_at,
                )
                session.add(row)
                # Flush (not refresh) inside the still-open transaction to populate the
                # autoincrement id -- a post-commit session.refresh() here isn't reliable
                # across this codebase's async session lifecycle (see other repositories,
                # none of which refresh after session.begin() closes).
                await session.flush()
                return self._to_stored(row)

    async def list_all(self) -> List[StoredScheduledCampaign]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(ScheduledCampaignRow).order_by(ScheduledCampaignRow.next_run_at)
            )
            return [self._to_stored(row) for row in result.scalars().all()]

    async def list_due(self, *, now: datetime) -> List[StoredScheduledCampaign]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(ScheduledCampaignRow)
                .where(ScheduledCampaignRow.enabled.is_(True))
                .where(ScheduledCampaignRow.next_run_at <= now)
                .order_by(ScheduledCampaignRow.next_run_at)
            )
            return [self._to_stored(row) for row in result.scalars().all()]

    async def get(self, schedule_id: int) -> Optional[StoredScheduledCampaign]:
        async with self._session_factory() as session:
            row = await session.get(ScheduledCampaignRow, schedule_id)
            return self._to_stored(row) if row is not None else None

    async def record_fired(
        self,
        schedule_id: int,
        *,
        job_id: str,
        ran_at: datetime,
        next_run_at: Optional[datetime],
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.get(ScheduledCampaignRow, schedule_id)
                if row is None:
                    return
                row.occurrences_run += 1
                row.last_run_at = ran_at
                row.last_job_id = job_id
                row.last_error = None
                if next_run_at is None:
                    row.enabled = False
                else:
                    row.next_run_at = next_run_at

    async def record_failed(self, schedule_id: int, *, error: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.get(ScheduledCampaignRow, schedule_id)
                if row is None:
                    return
                row.last_error = error

    async def cancel(self, schedule_id: int) -> Optional[StoredScheduledCampaign]:
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.get(ScheduledCampaignRow, schedule_id)
                if row is None:
                    return None
                row.enabled = False
                return self._to_stored(row)

    async def delete(self, schedule_id: int) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.get(ScheduledCampaignRow, schedule_id)
                if row is None:
                    return False
                await session.delete(row)
            return True

    @staticmethod
    def _to_stored(row: ScheduledCampaignRow) -> StoredScheduledCampaign:
        return StoredScheduledCampaign(
            id=row.id,
            name=row.name,
            campaign_type=row.campaign_type,
            payload=dict(row.payload),
            start_at=_as_utc(row.start_at),
            repeat_interval_hours=row.repeat_interval_hours,
            max_occurrences=row.max_occurrences,
            enabled=row.enabled,
            occurrences_run=row.occurrences_run,
            next_run_at=_as_utc(row.next_run_at),
            last_run_at=_as_utc_optional(row.last_run_at),
            last_job_id=row.last_job_id,
            last_error=row.last_error,
        )


async def ensure_scheduled_campaigns_table(session_factory: async_sessionmaker) -> None:
    """Create the scheduled_campaigns table when it does not exist yet."""
    engine = session_factory.kw["bind"]
    async with engine.begin() as connection:
        await connection.run_sync(ScheduledCampaignRow.__table__.create, checkfirst=True)
