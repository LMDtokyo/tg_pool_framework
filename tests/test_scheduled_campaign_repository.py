from datetime import datetime, timedelta, timezone

import pytest

from src.db.engine import build_engine_and_session_factory
from src.db.scheduled_campaign_repository import (
    ScheduledCampaignRepository,
    ensure_scheduled_campaigns_table,
)

pytestmark = pytest.mark.unit


@pytest.fixture
async def repository():
    engine, session_factory = build_engine_and_session_factory("sqlite+aiosqlite:///:memory:")
    await ensure_scheduled_campaigns_table(session_factory)
    try:
        yield ScheduledCampaignRepository(session_factory)
    finally:
        await engine.dispose()


def _future(hours: float = 1.0) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours)


async def _create(repository, **overrides):
    defaults = dict(
        name="Weekly promo",
        campaign_type="send_by_id",
        payload={"database_path": "audience.txt", "message": "hi"},
        start_at=_future(),
        repeat_interval_hours=None,
        max_occurrences=None,
    )
    defaults.update(overrides)
    return await repository.create(**defaults)


async def test_create_and_list_all(repository):
    created = await _create(repository)

    assert created.id > 0
    assert created.enabled is True
    assert created.occurrences_run == 0
    assert created.next_run_at == created.start_at

    listed = await repository.list_all()
    assert [c.id for c in listed] == [created.id]


async def test_list_due_excludes_future_and_disabled(repository):
    due_soon = await _create(repository, start_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    await _create(repository, start_at=_future(hours=5))
    disabled = await _create(repository, start_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    await repository.cancel(disabled.id)

    due = await repository.list_due(now=datetime.now(timezone.utc))

    assert [c.id for c in due] == [due_soon.id]


async def test_record_fired_reschedules_when_next_run_at_given(repository):
    campaign = await _create(repository, repeat_interval_hours=6)
    ran_at = datetime.now(timezone.utc)
    next_run = ran_at + timedelta(hours=6)

    await repository.record_fired(campaign.id, job_id="job-1", ran_at=ran_at, next_run_at=next_run)

    updated = await repository.get(campaign.id)
    assert updated.occurrences_run == 1
    assert updated.last_job_id == "job-1"
    assert updated.enabled is True
    assert updated.next_run_at == next_run


async def test_record_fired_disables_when_no_next_run(repository):
    campaign = await _create(repository)
    ran_at = datetime.now(timezone.utc)

    await repository.record_fired(campaign.id, job_id="job-1", ran_at=ran_at, next_run_at=None)

    updated = await repository.get(campaign.id)
    assert updated.enabled is False
    assert updated.occurrences_run == 1


async def test_record_failed_sets_last_error(repository):
    campaign = await _create(repository)

    await repository.record_failed(campaign.id, error="pool busy")

    updated = await repository.get(campaign.id)
    assert updated.last_error == "pool busy"


async def test_cancel_and_delete(repository):
    campaign = await _create(repository)

    cancelled = await repository.cancel(campaign.id)
    assert cancelled.enabled is False

    assert await repository.delete(campaign.id) is True
    assert await repository.get(campaign.id) is None
    assert await repository.delete(campaign.id) is False
