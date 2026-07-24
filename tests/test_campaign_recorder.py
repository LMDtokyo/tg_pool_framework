"""tests/test_campaign_recorder.py — CampaignRecorder EventBus integration."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from src.messaging.campaign_recorder import CampaignRecorder
from src.messaging.messaging_service import BatchReport
from src.monitoring.event_bus import EventBus, MessageDeliveredEvent

pytestmark = pytest.mark.unit


def make_repository() -> AsyncMock:
    repo = AsyncMock()
    repo.start_campaign = AsyncMock(return_value=42)
    repo.record_result = AsyncMock()
    repo.finish_campaign = AsyncMock()
    return repo


async def test_start_creates_campaign_via_repository():
    repo = make_repository()
    recorder = CampaignRecorder(repo, "@python", "Привет, {first_name}!")

    await recorder.start()

    repo.start_campaign.assert_called_once_with("@python", "Привет, {first_name}!")


async def test_subscribed_recorder_persists_message_delivered_events():
    repo = make_repository()
    recorder = CampaignRecorder(repo, "@python", "hi")
    await recorder.start()

    bus = EventBus()
    recorder.subscribe_to(bus)

    await bus.publish(MessageDeliveredEvent(
        worker_phone="+70001", recipient="alice", success=True, error="",
    ))
    await asyncio.sleep(0)  # let the fire-and-forget persist task run
    await asyncio.sleep(0)

    repo.record_result.assert_called_once_with(42, "alice", "+70001", True, None)


async def test_events_before_start_are_ignored():
    repo = make_repository()
    recorder = CampaignRecorder(repo, "@python", "hi")
    bus = EventBus()
    recorder.subscribe_to(bus)  # subscribed but start() never called

    await bus.publish(MessageDeliveredEvent(
        worker_phone="+70001", recipient="alice", success=True, error="",
    ))
    await asyncio.sleep(0)

    repo.record_result.assert_not_called()


async def test_finish_persists_totals_and_unsubscribes():
    repo = make_repository()
    recorder = CampaignRecorder(repo, "@python", "hi")
    await recorder.start()
    bus = EventBus()
    recorder.subscribe_to(bus)

    report = BatchReport(total=3, succeeded=2, failed=1)
    await recorder.finish(report, bus)

    repo.finish_campaign.assert_called_once_with(42, 3, 2, 1)

    # Unsubscribed — a later event must not be recorded
    await bus.publish(MessageDeliveredEvent(
        worker_phone="+70001", recipient="bob", success=True, error="",
    ))
    await asyncio.sleep(0)
    repo.record_result.assert_not_called()
