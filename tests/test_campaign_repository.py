"""tests/test_campaign_repository.py — CampaignRepository round-trip tests."""

import pytest

from src.db.campaign_repository import CampaignRepository
from src.db.engine import build_engine_and_session_factory
from src.db.models import Base

pytestmark = pytest.mark.unit


@pytest.fixture
async def repository():
    engine, session_factory = build_engine_and_session_factory("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield CampaignRepository(session_factory)
    finally:
        await engine.dispose()


async def test_start_campaign_returns_an_id(repository):
    campaign_id = await repository.start_campaign("@python", "Привет!")
    assert isinstance(campaign_id, int)


async def test_record_result_and_finish_campaign(repository):
    campaign_id = await repository.start_campaign("@python", "Привет!")

    await repository.record_result(campaign_id, "alice", "+70001", True, None)
    await repository.record_result(campaign_id, "bob", "+70001", False, "UserIsBlockedError")

    await repository.finish_campaign(campaign_id, total=2, succeeded=1, failed=1)

    # Verify via a second start_campaign for isolation, then inspect via raw query
    from sqlalchemy import select
    from src.db.models import CampaignResultRow, CampaignRow

    async with repository._session_factory() as session:
        campaign = (await session.execute(
            select(CampaignRow).where(CampaignRow.id == campaign_id)
        )).scalar_one()
        results = (await session.execute(
            select(CampaignResultRow).where(CampaignResultRow.campaign_id == campaign_id)
        )).scalars().all()

    assert campaign.total == 2
    assert campaign.succeeded == 1
    assert campaign.failed == 1
    assert campaign.finished_at is not None
    assert len(results) == 2
    assert {r.recipient for r in results} == {"alice", "bob"}


async def test_finish_campaign_unknown_id_is_a_noop(repository):
    await repository.finish_campaign(999999, total=0, succeeded=0, failed=0)  # must not raise
