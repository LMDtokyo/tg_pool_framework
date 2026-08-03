from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from telethon.errors import FloodWaitError, UserDeactivatedBanError
from telethon.tl.functions.messages import GetMessagesViewsRequest, SendReactionRequest

from tg_pool.accounts.proxy_safety import UnprotectedAccountsError
from tg_pool.accounts.warmup_policy import WarmupPolicy
from tg_pool.api.engagement import EngagementAlreadyRunningError, EngagementManager
from tg_pool.api.pool_guard import PoolAccessGuard
from tg_pool.config import AccountConfig, ProxyConfig

pytestmark = pytest.mark.unit


class _FakeRegistry:
    """Minimal registry.get(phone) stand-in -- only .first_seen is read by account_age_days()."""

    def __init__(self, first_seen_by_phone: dict) -> None:
        self._first_seen_by_phone = first_seen_by_phone

    def get(self, phone: str):
        first_seen = self._first_seen_by_phone.get(phone)
        return None if first_seen is None else SimpleNamespace(first_seen=first_seen)


def make_account(phone: str, proxy: ProxyConfig | None = None) -> AccountConfig:
    return AccountConfig(api_id=1, api_hash="hash", phone=phone, session_dir="sessions", proxy=proxy)


def make_client() -> MagicMock:
    client = AsyncMock()
    client.connect = AsyncMock()
    client.is_user_authorized = AsyncMock(return_value=True)
    client.disconnect = AsyncMock()
    # Telethon's is_connected() is genuinely synchronous; AsyncMock's child-mock
    # default is AsyncMock too, so this must be overridden explicitly or
    # `if client.is_connected():` in _disconnect() gets an unawaited coroutine.
    client.is_connected = MagicMock(return_value=True)
    client.get_input_entity = AsyncMock(return_value=MagicMock(name="peer"))
    return client


def test_start_rejects_unknown_action_type() -> None:
    manager = EngagementManager([make_account("+100")], PoolAccessGuard())
    with pytest.raises(ValueError, match="Unknown action_type"):
        manager.start(require_proxy=False, action_type="super_like", target_chat="@chan", target_message_id=1)


def test_start_requires_reaction_emoji_for_reaction_action() -> None:
    manager = EngagementManager([make_account("+100")], PoolAccessGuard())
    with pytest.raises(ValueError, match="reaction_emoji"):
        manager.start(require_proxy=False, action_type="reaction", target_chat="@chan", target_message_id=1)


def test_start_requires_poll_option_index_for_poll_vote_action() -> None:
    manager = EngagementManager([make_account("+100")], PoolAccessGuard())
    with pytest.raises(ValueError, match="poll_option_index"):
        manager.start(require_proxy=False, action_type="poll_vote", target_chat="@chan", target_message_id=1)


def test_start_requires_comment_text_for_comment_action() -> None:
    manager = EngagementManager([make_account("+100")], PoolAccessGuard())
    with pytest.raises(ValueError, match="comment_text"):
        manager.start(require_proxy=False, action_type="comment", target_chat="@chan", target_message_id=1)


async def test_start_caps_participants_to_max_total_accounts(monkeypatch) -> None:
    client = make_client()
    monkeypatch.setattr("tg_pool.api.engagement.ClientFactory.build", lambda _account: client)
    manager = EngagementManager(
        [make_account("+100"), make_account("+200"), make_account("+300")], PoolAccessGuard()
    )
    manager.start(require_proxy=False,
        action_type="view",
        target_chat="@chan",
        target_message_id=1,
        max_total_accounts=2,
        delay_min_sec=0,
        delay_max_sec=0,
    )
    assert len(manager._run.results) == 2
    await manager._run.task


async def test_second_start_while_running_raises(monkeypatch) -> None:
    client = make_client()
    monkeypatch.setattr("tg_pool.api.engagement.ClientFactory.build", lambda _account: client)
    manager = EngagementManager([make_account("+100")], PoolAccessGuard())

    # asyncio.create_task() schedules but never yields control here, so the freshly
    # started job's task has not run at all yet -- is_running is still guaranteed
    # True for this immediately-following second call, with no need to keep the
    # first job artificially stuck mid-connect.
    manager.start(require_proxy=False, action_type="view", target_chat="@chan", target_message_id=1, delay_min_sec=0, delay_max_sec=0)

    with pytest.raises(EngagementAlreadyRunningError):
        manager.start(require_proxy=False, action_type="view", target_chat="@chan", target_message_id=1)

    await manager._run.task


async def test_reaction_job_sends_correct_request_and_releases_pool(monkeypatch, tmp_path: Path) -> None:
    client = make_client()
    monkeypatch.setattr("tg_pool.api.engagement.ClientFactory.build", lambda _account: client)
    pool_guard = PoolAccessGuard()
    manager = EngagementManager([make_account("+100")], pool_guard)

    job_id = manager.start(require_proxy=False,
        action_type="reaction",
        target_chat="@chan",
        target_message_id=42,
        reaction_emoji="❤️",
        delay_min_sec=0,
        delay_max_sec=0,
        results_dir=str(tmp_path / "results"),
    )
    await manager._run.task

    status = manager.status()
    assert status["job_id"] == job_id
    assert status["succeeded"] == 1
    assert status["failed"] == 0
    assert status["finished"] is True
    assert Path(status["export_path"]).is_file()
    assert pool_guard.current_holder is None

    sent_request = client.await_args.args[0]
    assert isinstance(sent_request, SendReactionRequest)
    assert sent_request.msg_id == 42
    assert sent_request.reaction[0].emoticon == "❤️"


async def test_view_job_sends_increment_request(monkeypatch, tmp_path: Path) -> None:
    client = make_client()
    monkeypatch.setattr("tg_pool.api.engagement.ClientFactory.build", lambda _account: client)
    manager = EngagementManager([make_account("+100")], PoolAccessGuard())

    manager.start(require_proxy=False,
        action_type="view",
        target_chat="@chan",
        target_message_id=7,
        delay_min_sec=0,
        delay_max_sec=0,
        results_dir=str(tmp_path / "results"),
    )
    await manager._run.task

    sent_request = client.await_args.args[0]
    assert isinstance(sent_request, GetMessagesViewsRequest)
    assert sent_request.id == [7]
    assert sent_request.increment is True


async def test_poll_vote_job_clicks_the_chosen_option(monkeypatch, tmp_path: Path) -> None:
    client = make_client()
    poll_message = MagicMock()
    poll_message.poll = MagicMock()
    poll_message.click = AsyncMock()
    client.get_messages = AsyncMock(return_value=poll_message)
    monkeypatch.setattr("tg_pool.api.engagement.ClientFactory.build", lambda _account: client)
    manager = EngagementManager([make_account("+100")], PoolAccessGuard())

    manager.start(require_proxy=False,
        action_type="poll_vote",
        target_chat="@chan",
        target_message_id=9,
        poll_option_index=2,
        delay_min_sec=0,
        delay_max_sec=0,
        results_dir=str(tmp_path / "results"),
    )
    await manager._run.task

    poll_message.click.assert_awaited_once_with(2)
    assert manager.status()["succeeded"] == 1


async def test_poll_vote_job_fails_cleanly_when_message_has_no_poll(monkeypatch, tmp_path: Path) -> None:
    client = make_client()
    plain_message = MagicMock()
    plain_message.poll = None
    client.get_messages = AsyncMock(return_value=plain_message)
    monkeypatch.setattr("tg_pool.api.engagement.ClientFactory.build", lambda _account: client)
    manager = EngagementManager([make_account("+100")], PoolAccessGuard())

    manager.start(require_proxy=False,
        action_type="poll_vote",
        target_chat="@chan",
        target_message_id=9,
        poll_option_index=0,
        delay_min_sec=0,
        delay_max_sec=0,
        results_dir=str(tmp_path / "results"),
    )
    await manager._run.task

    status = manager.status()
    assert status["succeeded"] == 0
    assert status["failed"] == 1


async def test_comment_job_sends_message_with_comment_to(monkeypatch, tmp_path: Path) -> None:
    client = make_client()
    client.send_message = AsyncMock(return_value=MagicMock(id=1))
    monkeypatch.setattr("tg_pool.api.engagement.ClientFactory.build", lambda _account: client)
    manager = EngagementManager([make_account("+100")], PoolAccessGuard())

    manager.start(require_proxy=False,
        action_type="comment",
        target_chat="@chan",
        target_message_id=5,
        comment_text="Nice post!",
        delay_min_sec=0,
        delay_max_sec=0,
        results_dir=str(tmp_path / "results"),
    )
    await manager._run.task

    client.send_message.assert_awaited_once()
    kwargs = client.send_message.await_args.kwargs
    assert kwargs["comment_to"] == 5
    assert "Nice post" in client.send_message.await_args.args[1]


def test_warmup_throttles_a_young_account_below_its_configured_cap():
    registry = _FakeRegistry({"+100": datetime.now(timezone.utc)})
    policy = WarmupPolicy(duration_days=7, min_multiplier=3.0, max_daily_messages_day0=10, max_daily_messages_full=200)
    manager = EngagementManager(
        [make_account("+100")], PoolAccessGuard(), registry=registry, warmup_policy=policy
    )

    assert manager._capped_daily_limit("+100", 80) == 10
    assert manager._delay_multiplier("+100") == pytest.approx(3.0)


def test_warmup_does_not_tighten_the_cap_for_a_mature_account():
    registry = _FakeRegistry({"+100": datetime.now(timezone.utc) - timedelta(days=30)})
    policy = WarmupPolicy(duration_days=7, min_multiplier=3.0, max_daily_messages_day0=10, max_daily_messages_full=200)
    manager = EngagementManager(
        [make_account("+100")], PoolAccessGuard(), registry=registry, warmup_policy=policy
    )

    assert manager._capped_daily_limit("+100", 80) == 80
    assert manager._delay_multiplier("+100") == pytest.approx(1.0)


def test_no_warmup_policy_configured_means_no_throttling():
    manager = EngagementManager([make_account("+100")], PoolAccessGuard())

    assert manager._capped_daily_limit("+100", 80) == 80
    assert manager._delay_multiplier("+100") == 1.0


async def test_daily_cap_skip_is_recorded_and_does_not_connect(monkeypatch, tmp_path: Path) -> None:
    client = make_client()
    monkeypatch.setattr("tg_pool.api.engagement.ClientFactory.build", lambda _account: client)
    manager = EngagementManager(
        [make_account("+100")], PoolAccessGuard(), redis_client=object()
    )
    monkeypatch.setattr(manager, "_check_daily_cap", AsyncMock(return_value=False))

    manager.start(require_proxy=False,
        action_type="view",
        target_chat="@chan",
        target_message_id=1,
        delay_min_sec=0,
        delay_max_sec=0,
        results_dir=str(tmp_path / "results"),
    )
    await manager._run.task

    status = manager.status()
    assert status["skipped_daily_cap"] == 1
    assert status["succeeded"] == 0
    client.connect.assert_not_awaited()


async def test_auto_stop_ban_halts_remaining_accounts(monkeypatch, tmp_path: Path) -> None:
    banned_client = make_client()
    banned_client.side_effect = UserDeactivatedBanError(request=None)
    ok_client = make_client()

    clients_by_phone = {"+100": banned_client, "+200": ok_client}
    monkeypatch.setattr(
        "tg_pool.api.engagement.ClientFactory.build",
        lambda account: clients_by_phone[account.phone],
    )
    manager = EngagementManager(
        [make_account("+100"), make_account("+200")], PoolAccessGuard()
    )

    manager.start(require_proxy=False,
        action_type="view",
        target_chat="@chan",
        target_message_id=1,
        streams=1,
        auto_stop_ban=1,
        delay_min_sec=0,
        delay_max_sec=0,
        results_dir=str(tmp_path / "results"),
    )
    await manager._run.task

    status = manager.status()
    assert status["ban_count"] == 1
    # streams=1 serializes the two accounts; the second sees shutdown already set.
    assert status["succeeded"] == 0


def test_start_with_require_proxy_rejects_unproxied_senders() -> None:
    manager = EngagementManager([make_account("+100")], PoolAccessGuard())

    with pytest.raises(UnprotectedAccountsError, match=r"\+100"):
        manager.start(
            action_type="view",
            target_chat="@chan",
            target_message_id=1,
            require_proxy=True,
        )


async def test_status_reports_unproxied_senders_even_without_require_proxy(
    monkeypatch, tmp_path: Path
) -> None:
    client = make_client()
    monkeypatch.setattr("tg_pool.api.engagement.ClientFactory.build", lambda _account: client)
    manager = EngagementManager(
        [make_account("+100"), make_account("+200", proxy=ProxyConfig(host="1.2.3.4", port=1080))],
        PoolAccessGuard(),
    )

    manager.start(require_proxy=False,
        action_type="view",
        target_chat="@chan",
        target_message_id=1,
        delay_min_sec=0,
        delay_max_sec=0,
        results_dir=str(tmp_path / "results"),
    )
    await manager._run.task

    assert manager.status()["unproxied_senders"] == ["+100"]


async def test_ban_signal_is_recorded_against_the_sender_proxy(monkeypatch, tmp_path: Path) -> None:
    client = make_client()
    client.side_effect = UserDeactivatedBanError(request=None)
    monkeypatch.setattr("tg_pool.api.engagement.ClientFactory.build", lambda _account: client)
    proxy = ProxyConfig(host="1.2.3.4", port=1080, proxy_type="socks5")
    proxy_repository = AsyncMock()
    proxy_repository.record_ban_signal = AsyncMock(return_value=True)
    manager = EngagementManager(
        [make_account("+100", proxy=proxy)],
        PoolAccessGuard(),
        proxy_repository=proxy_repository,
    )

    manager.start(require_proxy=False,
        action_type="view",
        target_chat="@chan",
        target_message_id=1,
        delay_min_sec=0,
        delay_max_sec=0,
        results_dir=str(tmp_path / "results"),
    )
    await manager._run.task

    proxy_repository.record_ban_signal.assert_awaited_once_with(
        proxy_type="socks5", host="1.2.3.4", port=1080, username=""
    )


async def test_flood_wait_beyond_cap_fails_without_retrying(monkeypatch, tmp_path: Path) -> None:
    client = make_client()
    client.side_effect = FloodWaitError(request=None, capture=999)
    monkeypatch.setattr("tg_pool.api.engagement.ClientFactory.build", lambda _account: client)
    manager = EngagementManager([make_account("+100")], PoolAccessGuard())

    manager.start(require_proxy=False,
        action_type="view",
        target_chat="@chan",
        target_message_id=1,
        max_flood_wait_sec=1,
        delay_min_sec=0,
        delay_max_sec=0,
        results_dir=str(tmp_path / "results"),
    )
    await manager._run.task

    status = manager.status()
    assert status["floodwait_count"] == 1
    assert status["failed"] == 1
    assert "exceeds maximum timeout" in status["results"][0]["message"]
