"""
src/db/campaign_repository.py — CampaignRepository: durable history of send campaigns.

Mirrors the AccountRepository pattern (src/db/repository.py) — the only place
ORM details for campaigns are visible. CampaignRecorder (src/messaging/
campaign_recorder.py) is the caller; it never touches SQLAlchemy directly.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.db.models import CampaignResultRow, CampaignRow

logger = logging.getLogger(__name__)


class CampaignRepository:
    """Durable store for campaign runs and their per-recipient results."""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def start_campaign(self, target: str, message_preview: str) -> int:
        """Create a campaign row and return its id."""
        async with self._session_factory() as session:
            async with session.begin():
                row = CampaignRow(target=target, message_preview=message_preview)
                session.add(row)
                await session.flush()
                return row.id

    async def record_result(
        self,
        campaign_id: int,
        recipient: str,
        worker_phone: str,
        success: bool,
        error: Optional[str] = None,
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                session.add(CampaignResultRow(
                    campaign_id=campaign_id,
                    recipient=recipient,
                    worker_phone=worker_phone,
                    success=success,
                    error=error,
                ))

    async def finish_campaign(
        self, campaign_id: int, total: int, succeeded: int, failed: int
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(CampaignRow).where(CampaignRow.id == campaign_id)
                )
                row = result.scalar_one_or_none()
                if row is None:
                    logger.warning("finish_campaign: unknown campaign_id=%s", campaign_id)
                    return
                row.total = total
                row.succeeded = succeeded
                row.failed = failed
                row.finished_at = datetime.now(timezone.utc)
