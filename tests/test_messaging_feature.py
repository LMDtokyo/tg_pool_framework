"""tests/test_messaging_feature.py — src/features/messaging.py (MODE=send)."""

import asyncio
import logging
from unittest.mock import AsyncMock, patch

import pytest

import src.bootstrap as bootstrap
from src.config import AccountConfig, ProxyConfig
from src.features import messaging
from src.messaging.lua_storage import RedisRateLimiter
from src.messaging.messaging_service import BatchReport
from src.proxy.proxy_checker import ProxyState, ProxyType

pytestmark = pytest.mark.unit


def make_account(phone: str = "+1", proxy=None) -> AccountConfig:
    return AccountConfig(api_id=1, api_hash="h" * 32, phone=phone, proxy=proxy)


class TestBuildPayload:
    def test_defaults(self, monkeypatch):
        for var in ("TG_MESSAGE", "TG_MEDIA_PATH", "TG_MEDIA_PATHS", "TG_MEDIA_KIND",
                    "TG_BUTTONS", "TG_PARSE_MODE", "TG_SILENT", "TG_LINK_PREVIEW"):
            monkeypatch.delenv(var, raising=False)

        payload = messaging.build_payload()

        assert payload.media_paths is None
        assert payload.media_kind == "auto"
        assert payload.silent is False
        assert payload.link_preview is True

    def test_media_paths_parsed_from_csv(self, monkeypatch):
        monkeypatch.setenv("TG_MEDIA_PATHS", "a.jpg, b.jpg ,c.jpg")

        payload = messaging.build_payload()

        assert payload.media_paths == ["a.jpg", "b.jpg", "c.jpg"]

    def test_silent_and_link_preview_read_from_env(self, monkeypatch):
        monkeypatch.setenv("TG_SILENT", "1")
        monkeypatch.setenv("TG_LINK_PREVIEW", "0")

        payload = messaging.build_payload()

        assert payload.silent is True
        assert payload.link_preview is False

    def test_media_kind_read_from_env(self, monkeypatch):
        monkeypatch.setenv("TG_MEDIA_KIND", "voice")

        payload = messaging.build_payload()

        assert payload.media_kind == "voice"

    def test_forward_link_read_from_env(self, monkeypatch):
        monkeypatch.setenv("TG_FORWARD_LINK", "t.me/pythondev/5")

        payload = messaging.build_payload()

        assert payload.forward_link == "t.me/pythondev/5"

    def test_bot_relay_fields_parsed_from_env(self, monkeypatch):
        monkeypatch.setenv("TG_BOT_RELAY_USERNAME", "postbot")
        monkeypatch.setenv("TG_BOT_RELAY_MESSAGE_IDS", "10, 20,30")

        payload = messaging.build_payload()

        assert payload.bot_relay_username == "postbot"
        assert payload.bot_relay_message_ids == [10, 20, 30]

    def test_bot_relay_ids_default_none_when_unset(self, monkeypatch):
        monkeypatch.delenv("TG_BOT_RELAY_MESSAGE_IDS", raising=False)

        payload = messaging.build_payload()

        assert payload.bot_relay_message_ids is None

    def test_schedule_at_parsed_from_env(self, monkeypatch):
        monkeypatch.setenv("TG_SCHEDULE_AT", "2030-01-01T12:00:00")

        payload = messaging.build_payload()

        assert payload.schedule_at.isoformat() == "2030-01-01T12:00:00"

    def test_schedule_at_unset_defaults_to_none(self, monkeypatch):
        monkeypatch.delenv("TG_SCHEDULE_AT", raising=False)

        payload = messaging.build_payload()

        assert payload.schedule_at is None

    def test_schedule_at_invalid_falls_back_to_none(self, monkeypatch):
        monkeypatch.setenv("TG_SCHEDULE_AT", "not-a-date")

        payload = messaging.build_payload()

        assert payload.schedule_at is None

    def test_pin_after_send_read_from_env(self, monkeypatch):
        monkeypatch.setenv("TG_PIN_AFTER_SEND", "1")

        payload = messaging.build_payload()

        assert payload.pin_after_send is True

    def test_pin_after_send_defaults_false(self, monkeypatch):
        monkeypatch.delenv("TG_PIN_AFTER_SEND", raising=False)

        payload = messaging.build_payload()

        assert payload.pin_after_send is False


class TestBuildRateLimiter:
    def test_constructs_without_kwarg_mismatch(self, monkeypatch):
        """
        Regression: build_rate_limiter() used to call
        RedisRateLimiter(client, rate=..., burst=...) -- kwargs that don't
        exist on the real constructor (refill_rate/capacity).
        """
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        monkeypatch.setenv("RATE_LIMIT_TOKENS_PER_SEC", "2.5")
        monkeypatch.setenv("RATE_LIMIT_BURST", "7")
        monkeypatch.setenv("RATE_LIMIT_FAIL_MODE", "closed")

        limiter = messaging.build_rate_limiter()

        assert isinstance(limiter, RedisRateLimiter)
        assert limiter._refill_rate == 2.5
        assert limiter._capacity == 7
        assert limiter._fail_mode == "closed"


class TestBuildWarmupPolicy:
    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("WARMUP_ENABLED", raising=False)
        assert messaging.build_warmup_policy() is None

    def test_reads_env(self, monkeypatch):
        from src.accounts.warmup_policy import WarmupPolicy

        monkeypatch.setenv("WARMUP_ENABLED", "1")
        monkeypatch.setenv("WARMUP_DURATION_DAYS", "5")
        monkeypatch.setenv("WARMUP_MIN_MULTIPLIER", "4.0")
        monkeypatch.setenv("WARMUP_MAX_DAILY_DAY0", "3")
        monkeypatch.setenv("WARMUP_MAX_DAILY_FULL", "150")

        policy = messaging.build_warmup_policy()

        assert isinstance(policy, WarmupPolicy)
        assert policy.duration_days == 5.0
        assert policy.min_multiplier == 4.0
        assert policy.max_daily_messages_day0 == 3
        assert policy.max_daily_messages_full == 150


class TestBuildAutoResponder:
    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("AUTO_REPLY_ENABLED", raising=False)
        assert messaging.build_auto_responder() is None

    def test_enabled(self, monkeypatch, tmp_path):
        from src.messaging.auto_responder import AutoResponder

        monkeypatch.setenv("AUTO_REPLY_ENABLED", "1")
        monkeypatch.setenv("AUTO_REPLY_SCRIPTS_DIR", str(tmp_path))

        responder = messaging.build_auto_responder()

        assert isinstance(responder, AutoResponder)


class TestProxyPreflight:
    async def test_disabled_by_default_returns_accounts_unchanged(self, monkeypatch):
        monkeypatch.delenv("PROXY_PREFLIGHT_CHECK_ENABLED", raising=False)
        accounts = [make_account("+1")]

        result = await messaging._proxy_preflight(accounts, logging.getLogger("test"))

        assert result == accounts

    async def test_strict_excludes_dead_proxy_accounts(self, monkeypatch):
        monkeypatch.setenv("PROXY_PREFLIGHT_CHECK_ENABLED", "1")
        monkeypatch.setenv("PROXY_PREFLIGHT_STRICT", "1")
        proxy = ProxyConfig(host="1.2.3.4", port=1080)
        accounts = [make_account("+1", proxy), make_account("+2", None)]

        async def fake_check(accts, **kwargs):
            return {"+1": ProxyState(is_active=False, latency_ms=0.0, proxy_type=ProxyType.SOCKS5)}

        with patch("src.proxy.proxy_checker.check_account_proxies", side_effect=fake_check):
            result = await messaging._proxy_preflight(accounts, logging.getLogger("test"))

        assert [a.phone for a in result] == ["+2"]


class TestRun:
    async def test_no_target_entity_logs_error_and_returns(self, monkeypatch, caplog):
        caplog.set_level(logging.ERROR)
        monkeypatch.delenv("TG_TARGET_ENTITY", raising=False)

        await messaging.run(None, logging.getLogger("test"))

        assert any("TG_TARGET_ENTITY" in r.message for r in caplog.records)

    async def test_no_accounts_logs_error_and_returns(self, monkeypatch, caplog):
        caplog.set_level(logging.ERROR)
        monkeypatch.setenv("TG_TARGET_ENTITY", "@group")
        monkeypatch.delenv("SESSION_ENCRYPTION_ENABLED", raising=False)
        monkeypatch.delenv("PROXY_PREFLIGHT_CHECK_ENABLED", raising=False)
        monkeypatch.setattr(bootstrap, "load_accounts", lambda: ([], []))
        monkeypatch.setattr(bootstrap, "load_tdata_accounts", AsyncMock(return_value=[]))

        await messaging.run(None, logging.getLogger("test"))

        assert any("Аккаунты не найдены" in r.message for r in caplog.records)

    async def test_full_run_calls_orchestrate_multi_source_with_target(self, monkeypatch):
        monkeypatch.setenv("TG_TARGET_ENTITY", "@group")
        monkeypatch.setenv("MONITOR_ENABLED", "0")
        monkeypatch.delenv("SESSION_ENCRYPTION_ENABLED", raising=False)
        monkeypatch.delenv("PROXY_PREFLIGHT_CHECK_ENABLED", raising=False)
        monkeypatch.delenv("HEALTH_CHECK_ENABLED", raising=False)
        monkeypatch.delenv("COOLDOWN_SCHEDULER_ENABLED", raising=False)
        monkeypatch.delenv("PERIODIC_HEALTH_CHECK_ENABLED", raising=False)
        monkeypatch.delenv("REDIS_URL", raising=False)
        monkeypatch.delenv("DATABASE_URL", raising=False)

        monkeypatch.setattr(bootstrap, "load_accounts", lambda: ([make_account("+1")], []))
        monkeypatch.setattr(bootstrap, "load_tdata_accounts", AsyncMock(return_value=[]))

        captured = {}

        async def fake_orchestrate(**kwargs):
            captured.update(kwargs)
            return BatchReport(total=1, succeeded=1)

        with patch(
            "src.orchestrator.orchestrate_multi_source", new=AsyncMock(side_effect=fake_orchestrate)
        ):
            await messaging.run(asyncio.Event(), logging.getLogger("test"))

        assert captured["entity_identifiers"] == ["@group"]
        assert [a.phone for a in captured["accounts"]] == ["+1"]

    async def test_account_folder_filters_accounts(self, monkeypatch):
        from src.accounts.account_registry import AccountRegistry, RegistryEntry

        monkeypatch.setenv("TG_TARGET_ENTITY", "@group")
        monkeypatch.setenv("MONITOR_ENABLED", "0")
        monkeypatch.setenv("CAMPAIGN_ACCOUNT_FOLDER", "active")
        monkeypatch.delenv("SESSION_ENCRYPTION_ENABLED", raising=False)
        monkeypatch.delenv("PROXY_PREFLIGHT_CHECK_ENABLED", raising=False)
        monkeypatch.delenv("HEALTH_CHECK_ENABLED", raising=False)
        monkeypatch.delenv("COOLDOWN_SCHEDULER_ENABLED", raising=False)
        monkeypatch.delenv("PERIODIC_HEALTH_CHECK_ENABLED", raising=False)
        monkeypatch.delenv("REDIS_URL", raising=False)
        monkeypatch.delenv("DATABASE_URL", raising=False)

        accounts = [make_account("+1"), make_account("+2")]
        monkeypatch.setattr(bootstrap, "load_accounts", lambda: (accounts, []))
        monkeypatch.setattr(bootstrap, "load_tdata_accounts", AsyncMock(return_value=[]))

        folders = {"+1": "active", "+2": "cold"}
        monkeypatch.setattr(
            AccountRegistry, "get",
            lambda self, phone: RegistryEntry(account=make_account(phone), folder=folders.get(phone, "")),
        )

        captured = {}

        async def fake_orchestrate(**kwargs):
            captured.update(kwargs)
            return BatchReport(total=1, succeeded=1)

        with patch(
            "src.orchestrator.orchestrate_multi_source", new=AsyncMock(side_effect=fake_orchestrate)
        ):
            await messaging.run(asyncio.Event(), logging.getLogger("test"))

        assert [a.phone for a in captured["accounts"]] == ["+1"]

    async def test_account_folder_matching_nothing_logs_error_and_returns(self, monkeypatch, caplog):
        monkeypatch.setenv("TG_TARGET_ENTITY", "@group")
        monkeypatch.setenv("CAMPAIGN_ACCOUNT_FOLDER", "nonexistent")
        monkeypatch.delenv("PROXY_PREFLIGHT_CHECK_ENABLED", raising=False)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        caplog.set_level(logging.ERROR)

        monkeypatch.setattr(bootstrap, "load_accounts", lambda: ([make_account("+1")], []))
        monkeypatch.setattr(bootstrap, "load_tdata_accounts", AsyncMock(return_value=[]))

        with patch("src.orchestrator.orchestrate_multi_source", new=AsyncMock()) as mock_orchestrate:
            await messaging.run(asyncio.Event(), logging.getLogger("test"))

        mock_orchestrate.assert_not_called()
        assert any("nonexistent" in r.message for r in caplog.records)

    async def test_messages_per_account_range_read_from_env(self, monkeypatch):
        monkeypatch.setenv("TG_TARGET_ENTITY", "@group")
        monkeypatch.setenv("MONITOR_ENABLED", "0")
        monkeypatch.setenv("CAMPAIGN_MESSAGES_PER_ACCOUNT_MIN", "2")
        monkeypatch.setenv("CAMPAIGN_MESSAGES_PER_ACCOUNT_MAX", "10")
        monkeypatch.delenv("SESSION_ENCRYPTION_ENABLED", raising=False)
        monkeypatch.delenv("PROXY_PREFLIGHT_CHECK_ENABLED", raising=False)
        monkeypatch.delenv("HEALTH_CHECK_ENABLED", raising=False)
        monkeypatch.delenv("COOLDOWN_SCHEDULER_ENABLED", raising=False)
        monkeypatch.delenv("PERIODIC_HEALTH_CHECK_ENABLED", raising=False)
        monkeypatch.delenv("REDIS_URL", raising=False)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("CAMPAIGN_ACCOUNT_FOLDER", raising=False)

        monkeypatch.setattr(bootstrap, "load_accounts", lambda: ([make_account("+1")], []))
        monkeypatch.setattr(bootstrap, "load_tdata_accounts", AsyncMock(return_value=[]))

        captured = {}

        async def fake_orchestrate(**kwargs):
            captured.update(kwargs)
            return BatchReport(total=1, succeeded=1)

        with patch(
            "src.orchestrator.orchestrate_multi_source", new=AsyncMock(side_effect=fake_orchestrate)
        ):
            await messaging.run(asyncio.Event(), logging.getLogger("test"))

        assert captured["messages_per_account_min"] == 2
        assert captured["messages_per_account_max"] == 10

    async def test_messages_per_account_max_defaults_to_none(self, monkeypatch):
        monkeypatch.setenv("TG_TARGET_ENTITY", "@group")
        monkeypatch.setenv("MONITOR_ENABLED", "0")
        monkeypatch.delenv("CAMPAIGN_MESSAGES_PER_ACCOUNT_MAX", raising=False)
        monkeypatch.delenv("SESSION_ENCRYPTION_ENABLED", raising=False)
        monkeypatch.delenv("PROXY_PREFLIGHT_CHECK_ENABLED", raising=False)
        monkeypatch.delenv("HEALTH_CHECK_ENABLED", raising=False)
        monkeypatch.delenv("COOLDOWN_SCHEDULER_ENABLED", raising=False)
        monkeypatch.delenv("PERIODIC_HEALTH_CHECK_ENABLED", raising=False)
        monkeypatch.delenv("REDIS_URL", raising=False)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("CAMPAIGN_ACCOUNT_FOLDER", raising=False)

        monkeypatch.setattr(bootstrap, "load_accounts", lambda: ([make_account("+1")], []))
        monkeypatch.setattr(bootstrap, "load_tdata_accounts", AsyncMock(return_value=[]))

        captured = {}

        async def fake_orchestrate(**kwargs):
            captured.update(kwargs)
            return BatchReport(total=1, succeeded=1)

        with patch(
            "src.orchestrator.orchestrate_multi_source", new=AsyncMock(side_effect=fake_orchestrate)
        ):
            await messaging.run(asyncio.Event(), logging.getLogger("test"))

        assert captured["messages_per_account_max"] is None

    async def test_worker_batch_params_read_from_env(self, monkeypatch):
        monkeypatch.setenv("TG_TARGET_ENTITY", "@group")
        monkeypatch.setenv("MONITOR_ENABLED", "0")
        monkeypatch.setenv("CAMPAIGN_WORKER_BATCH_SIZE", "5")
        monkeypatch.setenv("CAMPAIGN_WORKER_BATCH_DELAY_SEC", "30")
        monkeypatch.delenv("SESSION_ENCRYPTION_ENABLED", raising=False)
        monkeypatch.delenv("PROXY_PREFLIGHT_CHECK_ENABLED", raising=False)
        monkeypatch.delenv("HEALTH_CHECK_ENABLED", raising=False)
        monkeypatch.delenv("COOLDOWN_SCHEDULER_ENABLED", raising=False)
        monkeypatch.delenv("PERIODIC_HEALTH_CHECK_ENABLED", raising=False)
        monkeypatch.delenv("REDIS_URL", raising=False)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("CAMPAIGN_ACCOUNT_FOLDER", raising=False)

        monkeypatch.setattr(bootstrap, "load_accounts", lambda: ([make_account("+1")], []))
        monkeypatch.setattr(bootstrap, "load_tdata_accounts", AsyncMock(return_value=[]))

        captured = {}

        async def fake_orchestrate(**kwargs):
            captured.update(kwargs)
            return BatchReport(total=1, succeeded=1)

        with patch(
            "src.orchestrator.orchestrate_multi_source", new=AsyncMock(side_effect=fake_orchestrate)
        ):
            await messaging.run(asyncio.Event(), logging.getLogger("test"))

        assert captured["worker_batch_size"] == 5
        assert captured["worker_batch_delay_sec"] == 30.0

    async def test_worker_batch_size_unset_defaults_to_none(self, monkeypatch):
        monkeypatch.setenv("TG_TARGET_ENTITY", "@group")
        monkeypatch.setenv("MONITOR_ENABLED", "0")
        monkeypatch.delenv("CAMPAIGN_WORKER_BATCH_SIZE", raising=False)
        monkeypatch.delenv("SESSION_ENCRYPTION_ENABLED", raising=False)
        monkeypatch.delenv("PROXY_PREFLIGHT_CHECK_ENABLED", raising=False)
        monkeypatch.delenv("HEALTH_CHECK_ENABLED", raising=False)
        monkeypatch.delenv("COOLDOWN_SCHEDULER_ENABLED", raising=False)
        monkeypatch.delenv("PERIODIC_HEALTH_CHECK_ENABLED", raising=False)
        monkeypatch.delenv("REDIS_URL", raising=False)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("CAMPAIGN_ACCOUNT_FOLDER", raising=False)

        monkeypatch.setattr(bootstrap, "load_accounts", lambda: ([make_account("+1")], []))
        monkeypatch.setattr(bootstrap, "load_tdata_accounts", AsyncMock(return_value=[]))

        captured = {}

        async def fake_orchestrate(**kwargs):
            captured.update(kwargs)
            return BatchReport(total=1, succeeded=1)

        with patch(
            "src.orchestrator.orchestrate_multi_source", new=AsyncMock(side_effect=fake_orchestrate)
        ):
            await messaging.run(asyncio.Event(), logging.getLogger("test"))

        assert captured["worker_batch_size"] is None

    async def test_repeat_every_hours_passed_to_run_with_repeat(self, monkeypatch):
        monkeypatch.setenv("TG_TARGET_ENTITY", "@group")
        monkeypatch.setenv("MONITOR_ENABLED", "0")
        monkeypatch.setenv("CAMPAIGN_REPEAT_EVERY_HOURS", "4.5")
        monkeypatch.delenv("SESSION_ENCRYPTION_ENABLED", raising=False)
        monkeypatch.delenv("PROXY_PREFLIGHT_CHECK_ENABLED", raising=False)
        monkeypatch.delenv("HEALTH_CHECK_ENABLED", raising=False)
        monkeypatch.delenv("COOLDOWN_SCHEDULER_ENABLED", raising=False)
        monkeypatch.delenv("PERIODIC_HEALTH_CHECK_ENABLED", raising=False)
        monkeypatch.delenv("REDIS_URL", raising=False)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("CAMPAIGN_ACCOUNT_FOLDER", raising=False)

        monkeypatch.setattr(bootstrap, "load_accounts", lambda: ([make_account("+1")], []))
        monkeypatch.setattr(bootstrap, "load_tdata_accounts", AsyncMock(return_value=[]))

        captured = {}

        async def fake_run_with_repeat(run_once, shutdown_event, repeat_every_hours):
            captured["repeat_every_hours"] = repeat_every_hours
            return await run_once()

        with (
            patch("src.orchestrator.orchestrate_multi_source",
                  new=AsyncMock(return_value=BatchReport(total=1, succeeded=1))),
            patch("src.orchestrator.run_with_repeat", new=fake_run_with_repeat),
        ):
            await messaging.run(asyncio.Event(), logging.getLogger("test"))

        assert captured["repeat_every_hours"] == 4.5

    async def test_repeat_every_hours_unset_defaults_to_none(self, monkeypatch):
        monkeypatch.setenv("TG_TARGET_ENTITY", "@group")
        monkeypatch.setenv("MONITOR_ENABLED", "0")
        monkeypatch.delenv("CAMPAIGN_REPEAT_EVERY_HOURS", raising=False)
        monkeypatch.delenv("SESSION_ENCRYPTION_ENABLED", raising=False)
        monkeypatch.delenv("PROXY_PREFLIGHT_CHECK_ENABLED", raising=False)
        monkeypatch.delenv("HEALTH_CHECK_ENABLED", raising=False)
        monkeypatch.delenv("COOLDOWN_SCHEDULER_ENABLED", raising=False)
        monkeypatch.delenv("PERIODIC_HEALTH_CHECK_ENABLED", raising=False)
        monkeypatch.delenv("REDIS_URL", raising=False)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("CAMPAIGN_ACCOUNT_FOLDER", raising=False)

        monkeypatch.setattr(bootstrap, "load_accounts", lambda: ([make_account("+1")], []))
        monkeypatch.setattr(bootstrap, "load_tdata_accounts", AsyncMock(return_value=[]))

        captured = {}

        async def fake_run_with_repeat(run_once, shutdown_event, repeat_every_hours):
            captured["repeat_every_hours"] = repeat_every_hours
            return await run_once()

        with (
            patch("src.orchestrator.orchestrate_multi_source",
                  new=AsyncMock(return_value=BatchReport(total=1, succeeded=1))),
            patch("src.orchestrator.run_with_repeat", new=fake_run_with_repeat),
        ):
            await messaging.run(asyncio.Event(), logging.getLogger("test"))

        assert captured["repeat_every_hours"] is None
