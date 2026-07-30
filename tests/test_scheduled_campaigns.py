import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from src.api.scheduled_campaigns import ScheduledCampaignManager
from src.api.send_by_id import SendByIdAlreadyRunningError
from src.db.engine import build_engine_and_session_factory
from src.db.scheduled_campaign_repository import (
    ScheduledCampaignRepository,
    ensure_scheduled_campaigns_table,
)

pytestmark = pytest.mark.unit


class _FakeManager:
    def __init__(self, *, raises=None):
        self.is_running = False
        self.started_with: list = []
        self._raises = raises
        self._next_job_id = 0

    def start(self, **kwargs) -> str:
        if self._raises is not None:
            raise self._raises
        self.started_with.append(kwargs)
        self._next_job_id += 1
        return f"job-{self._next_job_id}"


@pytest.fixture
async def repository():
    engine, session_factory = build_engine_and_session_factory("sqlite+aiosqlite:///:memory:")
    await ensure_scheduled_campaigns_table(session_factory)
    try:
        yield ScheduledCampaignRepository(session_factory)
    finally:
        await engine.dispose()


@pytest.fixture
def managers():
    return {"send_by_id": _FakeManager(), "send_by_numbers": _FakeManager()}


def _make_manager(repository, managers, poll_interval=0.01):
    return ScheduledCampaignManager(
        repository=repository,
        send_by_id_manager=managers["send_by_id"],
        send_by_numbers_manager=managers["send_by_numbers"],
        poll_interval=poll_interval,
    )


async def test_create_rejects_start_at_in_the_past(repository, managers):
    manager = _make_manager(repository, managers)

    with pytest.raises(ValueError, match="future"):
        await manager.create(
            name="late",
            campaign_type="send_by_id",
            payload={"database_path": "a.txt"},
            start_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            repeat_interval_hours=None,
            max_occurrences=None,
        )


async def test_create_rejects_unknown_campaign_type(repository, managers):
    manager = _make_manager(repository, managers)

    with pytest.raises(ValueError, match="campaign_type"):
        await manager.create(
            name="x",
            campaign_type="send_by_carrier_pigeon",
            payload={},
            start_at=datetime.now(timezone.utc) + timedelta(hours=1),
            repeat_interval_hours=None,
            max_occurrences=None,
        )


async def test_sweep_fires_a_due_one_shot_campaign_and_disables_it(repository, managers):
    manager = _make_manager(repository, managers)
    created = await manager.create(
        name="one-shot",
        campaign_type="send_by_id",
        payload={"database_path": "audience.txt", "message": "hi"},
        start_at=datetime.now(timezone.utc) + timedelta(milliseconds=50),
        repeat_interval_hours=None,
        max_occurrences=None,
    )
    await asyncio.sleep(0.08)

    await manager._sweep_once()

    assert managers["send_by_id"].started_with == [{"database_path": "audience.txt", "message": "hi"}]
    updated = await repository.get(created.id)
    assert updated.enabled is False
    assert updated.occurrences_run == 1
    assert updated.last_job_id == "job-1"


async def test_sweep_reschedules_a_repeating_campaign(repository, managers):
    manager = _make_manager(repository, managers)
    created = await manager.create(
        name="daily",
        campaign_type="send_by_numbers",
        payload={"phone_numbers": ["+1"]},
        start_at=datetime.now(timezone.utc) + timedelta(milliseconds=50),
        repeat_interval_hours=6,
        max_occurrences=None,
    )
    await asyncio.sleep(0.08)

    await manager._sweep_once()

    updated = await repository.get(created.id)
    assert updated.enabled is True
    assert updated.occurrences_run == 1
    assert updated.next_run_at > created.next_run_at + timedelta(hours=5)


async def test_sweep_disables_a_repeating_campaign_once_max_occurrences_reached(repository, managers):
    manager = _make_manager(repository, managers)
    created = await manager.create(
        name="twice-only",
        campaign_type="send_by_id",
        payload={"database_path": "a.txt"},
        start_at=datetime.now(timezone.utc) + timedelta(milliseconds=50),
        repeat_interval_hours=1,
        max_occurrences=1,
    )
    await asyncio.sleep(0.08)

    await manager._sweep_once()

    updated = await repository.get(created.id)
    assert updated.enabled is False
    assert updated.occurrences_run == 1


async def test_sweep_skips_and_retries_when_pool_is_busy(repository, managers):
    manager = _make_manager(repository, managers)
    created = await manager.create(
        name="busy",
        campaign_type="send_by_id",
        payload={"database_path": "a.txt"},
        start_at=datetime.now(timezone.utc) + timedelta(milliseconds=50),
        repeat_interval_hours=None,
        max_occurrences=None,
    )
    await asyncio.sleep(0.08)
    managers["send_by_id"].is_running = True

    await manager._sweep_once()

    assert managers["send_by_id"].started_with == []
    updated = await repository.get(created.id)
    assert updated.enabled is True
    assert updated.occurrences_run == 0
    assert updated.next_run_at == created.next_run_at


async def test_sweep_retries_when_the_manager_raises_already_running(repository, managers):
    managers["send_by_id"] = _FakeManager(raises=SendByIdAlreadyRunningError("busy"))
    manager = _make_manager(repository, managers)
    created = await manager.create(
        name="race",
        campaign_type="send_by_id",
        payload={"database_path": "a.txt"},
        start_at=datetime.now(timezone.utc) + timedelta(milliseconds=50),
        repeat_interval_hours=None,
        max_occurrences=None,
    )
    await asyncio.sleep(0.08)

    await manager._sweep_once()

    updated = await repository.get(created.id)
    assert updated.enabled is True
    assert updated.occurrences_run == 0


async def test_sweep_records_error_when_start_raises_unexpectedly(repository, managers):
    managers["send_by_id"] = _FakeManager(raises=ValueError("bad payload"))
    manager = _make_manager(repository, managers)
    created = await manager.create(
        name="broken",
        campaign_type="send_by_id",
        payload={"database_path": "a.txt"},
        start_at=datetime.now(timezone.utc) + timedelta(milliseconds=50),
        repeat_interval_hours=None,
        max_occurrences=None,
    )
    await asyncio.sleep(0.08)

    await manager._sweep_once()

    updated = await repository.get(created.id)
    assert updated.last_error == "bad payload"
    assert updated.occurrences_run == 0
    assert updated.enabled is True


async def test_run_sweeps_then_stops_on_shutdown(repository, managers):
    manager = _make_manager(repository, managers, poll_interval=0.05)
    await manager.create(
        name="loop",
        campaign_type="send_by_id",
        payload={"database_path": "a.txt"},
        start_at=datetime.now(timezone.utc) + timedelta(milliseconds=50),
        repeat_interval_hours=None,
        max_occurrences=None,
    )
    await asyncio.sleep(0.08)
    shutdown_event = asyncio.Event()

    async def _stop_soon():
        await asyncio.sleep(0.1)
        shutdown_event.set()

    stopper = asyncio.create_task(_stop_soon())
    await asyncio.wait_for(manager.run(shutdown_event), timeout=2.0)
    await stopper

    assert managers["send_by_id"].started_with != []
