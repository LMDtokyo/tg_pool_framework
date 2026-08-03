"""tests/test_orchestrator_multi_source.py — Tests for orchestrate_multi_source(), the pipeline main.py calls for personalized sends."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tg_pool.accounts.account_registry import AccountRegistry
from tg_pool.accounts.warmup_policy import WarmupPolicy
from tg_pool.config import AccountConfig, TimingPolicy
from tg_pool.extraction.data_extraction import ParsedUser
from tg_pool.messaging.messaging_service import BatchReport
from tg_pool.orchestrator import orchestrate_multi_source

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


def make_user(user_id: int, username: str, first_name: str = "", last_name: str = "") -> ParsedUser:
    return ParsedUser(user_id=user_id, username=username, first_name=first_name, last_name=last_name)


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


async def test_empty_accounts_returns_empty_report():
    report = await orchestrate_multi_source(
        accounts=[], entity_identifiers=["@test"], policy=FAST_POLICY,
    )
    assert report.total == 0


async def test_empty_entity_identifiers_returns_empty_report():
    report = await orchestrate_multi_source(
        accounts=[make_account()], entity_identifiers=[], policy=FAST_POLICY,
    )
    assert report.total == 0


async def test_full_pipeline_success_and_personalization_built():
    accounts = [make_account()]
    mock_pool = make_mock_pool()
    users = {make_user(1, "alice", "Alice", "Ivanova")}
    expected_report = BatchReport(total=1, succeeded=1, failed=0)

    captured_kwargs = {}

    async def mock_send(**kwargs):
        captured_kwargs.update(kwargs)
        return expected_report

    with (
        patch("tg_pool.orchestrator.ClientPool", return_value=mock_pool),
        patch("tg_pool.orchestrator.extract_users", new=AsyncMock(return_value=users)),
        patch("tg_pool.orchestrator.send_notifications", side_effect=mock_send),
    ):
        report = await orchestrate_multi_source(
            accounts=accounts,
            entity_identifiers=["@group"],
            policy=FAST_POLICY,
        )

    assert report.succeeded == 1
    assert captured_kwargs["recipients"] == {"alice"}
    assert captured_kwargs["personalization"] == {
        "alice": {"first_name": "Alice", "last_name": "Ivanova", "username": "alice"},
    }


async def test_no_users_skips_send():
    accounts = [make_account()]
    mock_pool = make_mock_pool()

    with (
        patch("tg_pool.orchestrator.ClientPool", return_value=mock_pool),
        patch("tg_pool.orchestrator.extract_users", new=AsyncMock(return_value=set())),
        patch("tg_pool.orchestrator.send_notifications") as mock_send,
    ):
        report = await orchestrate_multi_source(
            accounts=accounts, entity_identifiers=["@group"], policy=FAST_POLICY,
        )

    mock_send.assert_not_called()
    assert report.total == 0


async def test_users_without_username_excluded_from_personalization():
    accounts = [make_account()]
    mock_pool = make_mock_pool()
    users = {
        make_user(1, "alice", "Alice"),
        make_user(2, "", "NoUsername"),  # no username -> can't be a recipient
    }
    captured_kwargs = {}

    async def mock_send(**kwargs):
        captured_kwargs.update(kwargs)
        return BatchReport(total=1, succeeded=1)

    with (
        patch("tg_pool.orchestrator.ClientPool", return_value=mock_pool),
        patch("tg_pool.orchestrator.extract_users", new=AsyncMock(return_value=users)),
        patch("tg_pool.orchestrator.send_notifications", side_effect=mock_send),
    ):
        await orchestrate_multi_source(
            accounts=accounts, entity_identifiers=["@group"], policy=FAST_POLICY,
        )

    assert captured_kwargs["recipients"] == {"alice"}
    assert set(captured_kwargs["personalization"].keys()) == {"alice"}


async def test_warmup_multipliers_computed_from_registry():
    phone = "+79001234567"
    accounts = [make_account(phone)]
    mock_pool = make_mock_pool()
    users = {make_user(1, "alice", "Alice")}

    registry = AccountRegistry()
    await registry.register(accounts[0])  # first_seen set to "now" -> day 0

    policy = WarmupPolicy(duration_days=7.0, min_multiplier=3.0)
    captured_kwargs = {}

    async def mock_send(**kwargs):
        captured_kwargs.update(kwargs)
        return BatchReport(total=1, succeeded=1)

    with (
        patch("tg_pool.orchestrator.ClientPool", return_value=mock_pool),
        patch("tg_pool.orchestrator.extract_users", new=AsyncMock(return_value=users)),
        patch("tg_pool.orchestrator.send_notifications", side_effect=mock_send),
    ):
        await orchestrate_multi_source(
            accounts=accounts,
            entity_identifiers=["@group"],
            policy=FAST_POLICY,
            registry=registry,
            warmup_policy=policy,
        )

    assert captured_kwargs["warmup_multipliers"][phone] == pytest.approx(3.0, abs=0.05)
    assert captured_kwargs["warmup_limiters"] is None  # no redis_client passed


async def test_warmup_unknown_account_treated_as_day_zero():
    phone = "+79009999999"
    accounts = [make_account(phone)]
    mock_pool = make_mock_pool(worker_pairs=[(MagicMock(), phone)])
    users = {make_user(1, "alice", "Alice")}
    registry = AccountRegistry()  # phone never registered
    policy = WarmupPolicy(duration_days=7.0, min_multiplier=3.0)
    captured_kwargs = {}

    async def mock_send(**kwargs):
        captured_kwargs.update(kwargs)
        return BatchReport(total=1, succeeded=1)

    with (
        patch("tg_pool.orchestrator.ClientPool", return_value=mock_pool),
        patch("tg_pool.orchestrator.extract_users", new=AsyncMock(return_value=users)),
        patch("tg_pool.orchestrator.send_notifications", side_effect=mock_send),
    ):
        await orchestrate_multi_source(
            accounts=accounts,
            entity_identifiers=["@group"],
            policy=FAST_POLICY,
            registry=registry,
            warmup_policy=policy,
        )

    assert captured_kwargs["warmup_multipliers"][phone] == pytest.approx(3.0, abs=0.01)


async def test_warmup_limiters_built_when_redis_client_given():
    phone = "+79001234567"
    accounts = [make_account(phone)]
    mock_pool = make_mock_pool()
    users = {make_user(1, "alice", "Alice")}

    registry = AccountRegistry()
    await registry.register(accounts[0])
    policy = WarmupPolicy(duration_days=7.0, max_daily_messages_day0=10)
    fake_redis = MagicMock()
    fake_redis.register_script = MagicMock(side_effect=lambda *_a, **_k: AsyncMock())
    captured_kwargs = {}

    async def mock_send(**kwargs):
        captured_kwargs.update(kwargs)
        return BatchReport(total=1, succeeded=1)

    with (
        patch("tg_pool.orchestrator.ClientPool", return_value=mock_pool),
        patch("tg_pool.orchestrator.extract_users", new=AsyncMock(return_value=users)),
        patch("tg_pool.orchestrator.send_notifications", side_effect=mock_send),
    ):
        await orchestrate_multi_source(
            accounts=accounts,
            entity_identifiers=["@group"],
            policy=FAST_POLICY,
            registry=registry,
            warmup_policy=policy,
            redis_client=fake_redis,
        )

    from tg_pool.messaging.lua_storage import RedisRateLimiter
    assert isinstance(captured_kwargs["warmup_limiters"][phone], RedisRateLimiter)


async def test_no_warmup_policy_leaves_multipliers_none():
    accounts = [make_account()]
    mock_pool = make_mock_pool()
    users = {make_user(1, "alice", "Alice")}
    captured_kwargs = {}

    async def mock_send(**kwargs):
        captured_kwargs.update(kwargs)
        return BatchReport(total=1, succeeded=1)

    with (
        patch("tg_pool.orchestrator.ClientPool", return_value=mock_pool),
        patch("tg_pool.orchestrator.extract_users", new=AsyncMock(return_value=users)),
        patch("tg_pool.orchestrator.send_notifications", side_effect=mock_send),
    ):
        await orchestrate_multi_source(
            accounts=accounts, entity_identifiers=["@group"], policy=FAST_POLICY,
        )

    assert captured_kwargs["warmup_multipliers"] is None
    assert captured_kwargs["warmup_limiters"] is None


async def test_auto_responder_attached_and_detached():
    phone = "+79001234567"
    accounts = [make_account(phone)]
    fake_client = MagicMock()
    mock_pool = make_mock_pool(worker_pairs=[(fake_client, phone)])
    users = {make_user(1, "alice", "Alice")}
    responder = MagicMock()
    responder.attach = MagicMock()
    responder.detach_all = MagicMock()

    with (
        patch("tg_pool.orchestrator.ClientPool", return_value=mock_pool),
        patch("tg_pool.orchestrator.extract_users", new=AsyncMock(return_value=users)),
        patch("tg_pool.orchestrator.send_notifications", new=AsyncMock(return_value=BatchReport(total=1, succeeded=1))),
    ):
        await orchestrate_multi_source(
            accounts=accounts,
            entity_identifiers=["@group"],
            policy=FAST_POLICY,
            auto_responder=responder,
        )

    responder.attach.assert_called_once_with(fake_client, phone)
    responder.detach_all.assert_called_once()


async def test_auto_responder_detached_even_on_extraction_error():
    accounts = [make_account()]
    mock_pool = make_mock_pool()
    responder = MagicMock()

    with (
        patch("tg_pool.orchestrator.ClientPool", return_value=mock_pool),
        patch("tg_pool.orchestrator.extract_users", new=AsyncMock(side_effect=RuntimeError("boom"))),
    ):
        await orchestrate_multi_source(
            accounts=accounts,
            entity_identifiers=["@group"],
            policy=FAST_POLICY,
            auto_responder=responder,
        )

    responder.detach_all.assert_called_once()


async def test_no_auto_responder_is_a_noop():
    accounts = [make_account()]
    mock_pool = make_mock_pool()
    users = {make_user(1, "alice", "Alice")}

    with (
        patch("tg_pool.orchestrator.ClientPool", return_value=mock_pool),
        patch("tg_pool.orchestrator.extract_users", new=AsyncMock(return_value=users)),
        patch("tg_pool.orchestrator.send_notifications", new=AsyncMock(return_value=BatchReport(total=1, succeeded=1))),
    ):
        report = await orchestrate_multi_source(
            accounts=accounts, entity_identifiers=["@group"], policy=FAST_POLICY,
        )

    assert report.succeeded == 1


async def test_cleanup_called_even_on_extraction_error():
    accounts = [make_account()]
    mock_pool = make_mock_pool()

    with (
        patch("tg_pool.orchestrator.ClientPool", return_value=mock_pool),
        patch("tg_pool.orchestrator.extract_users", new=AsyncMock(side_effect=RuntimeError("boom"))),
    ):
        await orchestrate_multi_source(
            accounts=accounts, entity_identifiers=["@group"], policy=FAST_POLICY,
        )

    mock_pool.close_all.assert_called_once()


async def test_messages_per_account_range_passed_to_send_notifications():
    accounts = [make_account()]
    mock_pool = make_mock_pool()
    users = {make_user(1, "alice")}

    with (
        patch("tg_pool.orchestrator.ClientPool", return_value=mock_pool),
        patch("tg_pool.orchestrator.extract_users", new=AsyncMock(return_value=users)),
        patch(
            "tg_pool.orchestrator.send_notifications",
            new=AsyncMock(return_value=BatchReport(total=1, succeeded=1)),
        ) as mock_send,
    ):
        await orchestrate_multi_source(
            accounts=accounts, entity_identifiers=["@group"], policy=FAST_POLICY,
            messages_per_account_min=2, messages_per_account_max=5,
        )

    _, kwargs = mock_send.call_args
    assert kwargs["messages_per_account_min"] == 2
    assert kwargs["messages_per_account_max"] == 5


async def test_exclude_recipients_removed_from_recipient_set():
    accounts = [make_account()]
    mock_pool = make_mock_pool()
    users = {make_user(1, "alice"), make_user(2, "bob"), make_user(3, "carol")}

    captured_kwargs = {}

    async def mock_send(**kwargs):
        captured_kwargs.update(kwargs)
        return BatchReport(total=2, succeeded=2)

    with (
        patch("tg_pool.orchestrator.ClientPool", return_value=mock_pool),
        patch("tg_pool.orchestrator.extract_users", new=AsyncMock(return_value=users)),
        patch("tg_pool.orchestrator.send_notifications", side_effect=mock_send),
    ):
        await orchestrate_multi_source(
            accounts=accounts, entity_identifiers=["@group"], policy=FAST_POLICY,
            exclude_recipients={"alice"},
        )

    assert captured_kwargs["recipients"] == {"bob", "carol"}


async def test_exclude_recipients_covering_everyone_skips_send():
    accounts = [make_account()]
    mock_pool = make_mock_pool()
    users = {make_user(1, "alice")}

    with (
        patch("tg_pool.orchestrator.ClientPool", return_value=mock_pool),
        patch("tg_pool.orchestrator.extract_users", new=AsyncMock(return_value=users)),
        patch("tg_pool.orchestrator.send_notifications") as mock_send,
    ):
        report = await orchestrate_multi_source(
            accounts=accounts, entity_identifiers=["@group"], policy=FAST_POLICY,
            exclude_recipients={"alice"},
        )

    mock_send.assert_not_called()
    assert report.total == 0
