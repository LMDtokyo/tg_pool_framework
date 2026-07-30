"""
src/api/scheduled_campaigns.py — Restart-durable scheduling for send-by-ID and
send-by-numbers campaigns.

SendByIdManager/SendByNumbersManager already support schedule_at (a Telegram
"send later" flag) and repeat_every_hours (an in-process repeat loop), but
neither survives a backend restart -- both only exist for as long as the
asyncio task they were started on stays alive. ScheduledCampaignManager fills
that gap: it persists "run this campaign at this wall-clock time, optionally
every N hours" to the database, then sweeps for due rows on a fixed interval
(same shutdown_event poll-loop idiom as CooldownScheduler/PeriodicHealthScheduler)
and calls the matching manager's start() when one comes due.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from src.api.send_by_id import SendByIdAlreadyRunningError, SendByIdManager
from src.api.send_by_numbers import SendByNumbersAlreadyRunningError, SendByNumbersManager
from src.db.scheduled_campaign_repository import (
    ScheduledCampaignRepository,
    StoredScheduledCampaign,
)

logger = logging.getLogger(__name__)

CAMPAIGN_TYPES = ("send_by_id", "send_by_numbers")


class ScheduledCampaignManager:
    """Owns the scheduled_campaigns table and the sweep loop that fires due rows."""

    def __init__(
        self,
        repository: ScheduledCampaignRepository,
        send_by_id_manager: SendByIdManager,
        send_by_numbers_manager: SendByNumbersManager,
        poll_interval: float = 30.0,
    ) -> None:
        self._repository = repository
        self._managers = {
            "send_by_id": send_by_id_manager,
            "send_by_numbers": send_by_numbers_manager,
        }
        self._poll_interval = poll_interval

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
        if campaign_type not in CAMPAIGN_TYPES:
            raise ValueError(f"Unknown campaign_type: {campaign_type!r}")
        if start_at.tzinfo is None:
            start_at = start_at.replace(tzinfo=timezone.utc)
        if start_at <= datetime.now(timezone.utc):
            raise ValueError("start_at must be in the future.")
        if repeat_interval_hours is not None and repeat_interval_hours <= 0:
            raise ValueError("repeat_interval_hours must be positive.")
        if max_occurrences is not None and max_occurrences < 1:
            raise ValueError("max_occurrences must be at least 1.")

        return await self._repository.create(
            name=name.strip() or campaign_type,
            campaign_type=campaign_type,
            payload=payload,
            start_at=start_at,
            repeat_interval_hours=repeat_interval_hours,
            max_occurrences=max_occurrences,
        )

    async def list(self) -> list[StoredScheduledCampaign]:
        return await self._repository.list_all()

    async def cancel(self, schedule_id: int) -> Optional[StoredScheduledCampaign]:
        return await self._repository.cancel(schedule_id)

    async def delete(self, schedule_id: int) -> bool:
        return await self._repository.delete(schedule_id)

    async def run(self, shutdown_event: asyncio.Event) -> None:
        """Sweep for due campaigns on a fixed interval until shutdown_event is set."""
        logger.info(
            "ScheduledCampaignManager: started (poll_interval=%.0fs)", self._poll_interval
        )
        while not shutdown_event.is_set():
            try:
                await self._sweep_once()
            except Exception:
                logger.exception("ScheduledCampaignManager: sweep failed")

            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(shutdown_event.wait(), timeout=self._poll_interval)

        logger.info("ScheduledCampaignManager: stopped")

    async def _sweep_once(self) -> None:
        now = datetime.now(timezone.utc)
        due = await self._repository.list_due(now=now)
        for campaign in due:
            await self._fire(campaign, now=now)

    async def _fire(self, campaign: StoredScheduledCampaign, *, now: datetime) -> None:
        manager = self._managers[campaign.campaign_type]
        if manager.is_running:
            # Pool is busy (another manual or scheduled job holds it) -- leave
            # next_run_at untouched so this campaign is retried on the next sweep.
            logger.info(
                "ScheduledCampaignManager: campaign %d (%s) due but pool busy, will retry.",
                campaign.id,
                campaign.name,
            )
            return

        try:
            job_id = manager.start(**campaign.payload)
        except (SendByIdAlreadyRunningError, SendByNumbersAlreadyRunningError):
            logger.info(
                "ScheduledCampaignManager: campaign %d (%s) lost a race for the pool, will retry.",
                campaign.id,
                campaign.name,
            )
            return
        except Exception as exc:
            logger.exception(
                "ScheduledCampaignManager: campaign %d (%s) failed to start", campaign.id, campaign.name
            )
            await self._repository.record_failed(campaign.id, error=str(exc))
            return

        next_run_at = self._compute_next_run(campaign, now=now)
        await self._repository.record_fired(
            campaign.id, job_id=job_id, ran_at=now, next_run_at=next_run_at
        )
        logger.info(
            "ScheduledCampaignManager: campaign %d (%s) fired as job %s.",
            campaign.id,
            campaign.name,
            job_id,
        )

    @staticmethod
    def _compute_next_run(campaign: StoredScheduledCampaign, *, now: datetime) -> Optional[datetime]:
        if campaign.repeat_interval_hours is None:
            return None
        occurrences_after_this_run = campaign.occurrences_run + 1
        if (
            campaign.max_occurrences is not None
            and occurrences_after_this_run >= campaign.max_occurrences
        ):
            return None
        return now + timedelta(hours=campaign.repeat_interval_hours)
