"""
tests/test_orchestrator_extraction_only.py — Tests for orchestrate_extraction_only().

Same mocking style as test_orchestrator_multi_source.py (ClientPool / extract_users
fully mocked — no network). This is the parsing-only counterpart of
orchestrate_multi_source(): it must never call send_notifications.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis as fakeredis_aio
import pytest

from src.config import AccountConfig, TimingPolicy
from src.extraction.data_extraction import ParsedUser
from src.extraction.exporter import DataExporter
from src.extraction.user_filter import IsPremiumFilter, UserFilterPipeline
from src.orchestrator import orchestrate_extraction_only

FAST_POLICY = TimingPolicy(
    base_delay_sec=0.0,
    jitter_sec=0.0,
    inter_message_delay_sec=0.0,
    inter_message_jitter_sec=0.0,
    startup_jitter_max_sec=0.0,
    max_flood_retries=3,
)


def make_account(phone: str = "+79001234567") -> AccountConfig:
    return AccountConfig(api_id=12345, api_hash="a" * 32, phone=phone)


def make_user(user_id: int, username: str, premium: bool = False) -> ParsedUser:
    return ParsedUser(user_id=user_id, username=username, premium=premium)


def make_mock_pool(worker_pairs=None) -> MagicMock:
    if worker_pairs is None:
        worker_pairs = [(MagicMock(), "+79001234567")]
    pool = MagicMock()
    pool.initialize = AsyncMock()
    pool.close_all = AsyncMock()
    pool.get_worker_pairs = MagicMock(return_value=worker_pairs)
    pool.__bool__ = MagicMock(return_value=bool(worker_pairs))
    pool.__len__ = MagicMock(return_value=len(worker_pairs))
    return pool


async def test_empty_accounts_returns_empty_exporter():
    exporter = await orchestrate_extraction_only(
        accounts=[], entity_identifiers=["@test"], policy=FAST_POLICY,
    )
    assert isinstance(exporter, DataExporter)
    assert exporter.total == 0


async def test_empty_entity_identifiers_returns_empty_exporter():
    exporter = await orchestrate_extraction_only(
        accounts=[make_account()], entity_identifiers=[], policy=FAST_POLICY,
    )
    assert exporter.total == 0


async def test_never_calls_send_notifications():
    accounts = [make_account()]
    mock_pool = make_mock_pool()
    users = {make_user(1, "alice"), make_user(2, "bob")}

    with (
        patch("src.orchestrator.ClientPool", return_value=mock_pool),
        patch("src.orchestrator.extract_users", new=AsyncMock(return_value=users)),
        patch("src.orchestrator.send_notifications") as mock_send,
    ):
        exporter = await orchestrate_extraction_only(
            accounts=accounts, entity_identifiers=["@group"], policy=FAST_POLICY,
        )

    mock_send.assert_not_called()
    assert exporter.total == 2


async def test_collected_users_land_in_provided_exporter():
    accounts = [make_account()]
    mock_pool = make_mock_pool()
    users = {make_user(1, "alice"), make_user(2, "bob")}
    exporter = DataExporter()

    with (
        patch("src.orchestrator.ClientPool", return_value=mock_pool),
        patch("src.orchestrator.extract_users", new=AsyncMock(return_value=users)),
    ):
        result = await orchestrate_extraction_only(
            accounts=accounts, entity_identifiers=["@group"], exporter=exporter, policy=FAST_POLICY,
        )

    assert result is exporter
    assert exporter.total == 2


async def test_user_filter_determines_exported_set():
    accounts = [make_account()]
    mock_pool = make_mock_pool()
    users = {
        make_user(1, "alice", premium=True),
        make_user(2, "bob", premium=False),
    }
    pipeline = UserFilterPipeline([IsPremiumFilter()])

    with (
        patch("src.orchestrator.ClientPool", return_value=mock_pool),
        patch("src.orchestrator.extract_users", new=AsyncMock(return_value=users)),
    ):
        exporter = await orchestrate_extraction_only(
            accounts=accounts, entity_identifiers=["@group"], user_filter=pipeline, policy=FAST_POLICY,
        )

    assert exporter.total == 1
    assert exporter.to_dataframe().iloc[0]["Юзернейм"] == "@alice"


async def test_no_users_still_returns_valid_exporter():
    accounts = [make_account()]
    mock_pool = make_mock_pool()

    with (
        patch("src.orchestrator.ClientPool", return_value=mock_pool),
        patch("src.orchestrator.extract_users", new=AsyncMock(return_value=set())),
    ):
        exporter = await orchestrate_extraction_only(
            accounts=accounts, entity_identifiers=["@group"], policy=FAST_POLICY,
        )

    assert exporter.total == 0


async def test_no_active_clients_after_init_returns_empty_exporter():
    accounts = [make_account()]
    mock_pool = make_mock_pool(worker_pairs=[])

    with patch("src.orchestrator.ClientPool", return_value=mock_pool):
        exporter = await orchestrate_extraction_only(
            accounts=accounts, entity_identifiers=["@group"], policy=FAST_POLICY,
        )

    assert exporter.total == 0


async def test_multiple_sources_distributed_and_merged():
    accounts = [make_account("+1"), make_account("+2")]
    mock_pool = make_mock_pool(worker_pairs=[(MagicMock(), "+1"), (MagicMock(), "+2")])

    async def fake_extract_users(client, entity_id, strategy, policy):
        uid = abs(hash(entity_id)) % 1000
        return {ParsedUser(user_id=uid, username=entity_id.strip("@"), source=entity_id)}

    with (
        patch("src.orchestrator.ClientPool", return_value=mock_pool),
        patch("src.orchestrator.extract_users", new=AsyncMock(side_effect=fake_extract_users)),
    ):
        exporter = await orchestrate_extraction_only(
            accounts=accounts,
            entity_identifiers=["@group_a", "@group_b"],
            policy=FAST_POLICY,
        )

    assert set(exporter.sources) == {"@group_a", "@group_b"}


# ---------------------------------------------------------------------------
# Redis dedup (redis_client / job_key) — resumable parsing
# ---------------------------------------------------------------------------

async def test_redis_dedup_skips_already_seen_users_on_resumed_run():
    accounts = [make_account()]
    mock_pool = make_mock_pool()
    users = {make_user(1, "alice"), make_user(2, "bob")}
    redis_client = fakeredis_aio.FakeRedis()

    with (
        patch("src.orchestrator.ClientPool", return_value=mock_pool),
        patch("src.orchestrator.extract_users", new=AsyncMock(return_value=users)),
    ):
        first_run = await orchestrate_extraction_only(
            accounts=accounts, entity_identifiers=["@group"], policy=FAST_POLICY,
            redis_client=redis_client, job_key="job-1",
        )
        second_run = await orchestrate_extraction_only(
            accounts=accounts, entity_identifiers=["@group"], policy=FAST_POLICY,
            redis_client=redis_client, job_key="job-1",
        )

    assert first_run.total == 2
    assert second_run.total == 0


async def test_redis_dedup_only_yields_newly_seen_users_on_second_run():
    accounts = [make_account()]
    mock_pool = make_mock_pool()
    redis_client = fakeredis_aio.FakeRedis()

    with patch("src.orchestrator.ClientPool", return_value=mock_pool):
        with patch("src.orchestrator.extract_users", new=AsyncMock(return_value={make_user(1, "alice")})):
            await orchestrate_extraction_only(
                accounts=accounts, entity_identifiers=["@group"], policy=FAST_POLICY,
                redis_client=redis_client, job_key="job-1",
            )

        with patch(
            "src.orchestrator.extract_users",
            new=AsyncMock(return_value={make_user(1, "alice"), make_user(2, "bob")}),
        ):
            second_run = await orchestrate_extraction_only(
                accounts=accounts, entity_identifiers=["@group"], policy=FAST_POLICY,
                redis_client=redis_client, job_key="job-1",
            )

    assert second_run.total == 1
    assert second_run.to_dataframe().iloc[0]["Юзернейм"] == "@bob"


async def test_redis_dedup_default_job_key_is_stable_across_runs_with_same_sources():
    """No explicit job_key given -> the deterministic hash of sources still dedups."""
    accounts = [make_account()]
    mock_pool = make_mock_pool()
    users = {make_user(1, "alice")}
    redis_client = fakeredis_aio.FakeRedis()

    with (
        patch("src.orchestrator.ClientPool", return_value=mock_pool),
        patch("src.orchestrator.extract_users", new=AsyncMock(return_value=users)),
    ):
        first_run = await orchestrate_extraction_only(
            accounts=accounts, entity_identifiers=["@group"], policy=FAST_POLICY,
            redis_client=redis_client,
        )
        second_run = await orchestrate_extraction_only(
            accounts=accounts, entity_identifiers=["@group"], policy=FAST_POLICY,
            redis_client=redis_client,
        )

    assert first_run.total == 1
    assert second_run.total == 0


async def test_no_redis_client_means_no_dedup_across_runs():
    accounts = [make_account()]
    mock_pool = make_mock_pool()
    users = {make_user(1, "alice")}

    with (
        patch("src.orchestrator.ClientPool", return_value=mock_pool),
        patch("src.orchestrator.extract_users", new=AsyncMock(return_value=users)),
    ):
        first_run = await orchestrate_extraction_only(
            accounts=accounts, entity_identifiers=["@group"], policy=FAST_POLICY,
        )
        second_run = await orchestrate_extraction_only(
            accounts=accounts, entity_identifiers=["@group"], policy=FAST_POLICY,
        )

    assert first_run.total == 1
    assert second_run.total == 1


# ---------------------------------------------------------------------------
# strategy_selector gating: only active when strategy is None AND there's
# more than one entity
# ---------------------------------------------------------------------------

async def test_strategy_selector_used_when_strategy_none_and_multiple_entities():
    from src.extraction.entity_resolver import EntityInfo, EntityKind

    accounts = [make_account()]
    mock_pool = make_mock_pool()
    picked_strategy = MagicMock(name="picked_strategy")
    selector = MagicMock()
    selector.select.return_value = picked_strategy
    info = EntityInfo(weight=1.0, kind=EntityKind.CHAT, is_forum=False)

    used_strategies = []

    async def fake_extract_users(client, entity_id, strategy, policy):
        used_strategies.append(strategy)
        return set()

    with (
        patch("src.orchestrator.ClientPool", return_value=mock_pool),
        patch("src.orchestrator.describe_entity", new=AsyncMock(return_value=info)),
        patch("src.orchestrator.extract_users", new=AsyncMock(side_effect=fake_extract_users)),
    ):
        await orchestrate_extraction_only(
            accounts=accounts,
            entity_identifiers=["@a", "@b"],
            policy=FAST_POLICY,
            strategy_selector=selector,
        )

    assert used_strategies == [picked_strategy, picked_strategy]
    assert selector.select.call_count == 2


async def test_strategy_selector_ignored_with_explicit_strategy():
    accounts = [make_account()]
    mock_pool = make_mock_pool()
    selector = MagicMock()
    explicit_strategy = MagicMock()

    with (
        patch("src.orchestrator.ClientPool", return_value=mock_pool),
        patch("src.orchestrator.describe_entity", new=AsyncMock()) as mock_describe,
        patch("src.orchestrator.extract_users", new=AsyncMock(return_value=set())),
    ):
        await orchestrate_extraction_only(
            accounts=accounts,
            entity_identifiers=["@a", "@b"],
            strategy=explicit_strategy,
            policy=FAST_POLICY,
            strategy_selector=selector,
        )

    mock_describe.assert_not_called()
    selector.select.assert_not_called()


async def test_strategy_selector_ignored_with_single_entity():
    accounts = [make_account()]
    mock_pool = make_mock_pool()
    selector = MagicMock()

    with (
        patch("src.orchestrator.ClientPool", return_value=mock_pool),
        patch("src.orchestrator.describe_entity", new=AsyncMock()) as mock_describe,
        patch("src.orchestrator.extract_users", new=AsyncMock(return_value=set())),
    ):
        await orchestrate_extraction_only(
            accounts=accounts,
            entity_identifiers=["@only_one"],
            policy=FAST_POLICY,
            strategy_selector=selector,
        )

    mock_describe.assert_not_called()
    selector.select.assert_not_called()
