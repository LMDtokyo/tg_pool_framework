"""
src/messaging/campaign_recorder.py — Durable history of a single send campaign.

Decoupled from the orchestrator the same way LiveMonitor is (src/monitoring/monitor.py):
subscribes to MessageDeliveredEvent on the EventBus instead of the pipeline calling
it directly. A CampaignRepository hiccup must never break the send pipeline, so
writes are fire-and-forget, same pattern as AccountRegistry._persist()
(src/accounts/account_registry.py).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional

from src.db.campaign_repository import CampaignRepository
from src.monitoring.event_bus import EventBus, MessageDeliveredEvent

if TYPE_CHECKING:
    from src.messaging.messaging_service import BatchReport

logger = logging.getLogger(__name__)

_PREVIEW_LEN = 200


class CampaignRecorder:
    """Persists one campaign's lifecycle: start() -> per-message rows -> finish()."""

    def __init__(self, repository: CampaignRepository, target: str, message_text: str) -> None:
        self._repository = repository
        self._target = target
        self._message_preview = message_text[:_PREVIEW_LEN]
        self._campaign_id: Optional[int] = None
        self._subscription_token: Optional[int] = None

    async def start(self) -> None:
        self._campaign_id = await self._repository.start_campaign(
            self._target, self._message_preview
        )
        logger.info(
            "CampaignRecorder: started campaign_id=%s target=%s",
            self._campaign_id, self._target,
        )

    def subscribe_to(self, event_bus: EventBus) -> None:
        self._subscription_token = event_bus.subscribe(
            MessageDeliveredEvent, self._on_message_delivered
        )

    def _on_message_delivered(self, event: MessageDeliveredEvent) -> None:
        if self._campaign_id is None:
            return
        campaign_id = self._campaign_id

        async def _write() -> None:
            try:
                await self._repository.record_result(
                    campaign_id, event.recipient, event.worker_phone,
                    event.success, event.error or None,
                )
            except Exception:
                logger.exception(
                    "CampaignRecorder: failed to persist result for %s", event.recipient
                )

        asyncio.create_task(_write(), name=f"campaign-result-{event.recipient}")

    async def finish(self, report: "BatchReport", event_bus: Optional[EventBus] = None) -> None:
        if event_bus is not None and self._subscription_token is not None:
            event_bus.unsubscribe(self._subscription_token)
        if self._campaign_id is None:
            return
        await self._repository.finish_campaign(
            self._campaign_id, report.total, report.succeeded, report.failed
        )
        logger.info("CampaignRecorder: finished campaign_id=%s %s", self._campaign_id, report)
