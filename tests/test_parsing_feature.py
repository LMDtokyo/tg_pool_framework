"""tests/test_parsing_feature.py — src/features/parsing.py (MODE=parse)."""

import logging
from unittest.mock import AsyncMock, patch

import pytest

import src.bootstrap as bootstrap
from src.config import AccountConfig, ProxyConfig
from src.extraction.data_extraction import ParsedUser
from src.extraction.exporter import DataExporter
from src.features import parsing
from src.proxy.proxy_checker import ProxyState, ProxyType

pytestmark = pytest.mark.unit


def make_account(phone: str = "+1", proxy=None) -> AccountConfig:
    return AccountConfig(api_id=1, api_hash="h" * 32, phone=phone, proxy=proxy)


class TestBuildParsingStrategy:
    def test_defaults_to_group_members(self, monkeypatch):
        from src.extraction.data_extraction import GroupMembersStrategy

        monkeypatch.delenv("PARSE_STRATEGY", raising=False)
        assert isinstance(parsing.build_parsing_strategy(), GroupMembersStrategy)

    def test_topic_requires_topic_id(self, monkeypatch):
        monkeypatch.setenv("PARSE_STRATEGY", "topic")
        monkeypatch.delenv("PARSE_TOPIC_ID", raising=False)
        with pytest.raises(ValueError, match="PARSE_TOPIC_ID"):
            parsing.build_parsing_strategy()

    def test_topic_reads_topic_id(self, monkeypatch):
        from src.extraction.data_extraction import TopicMessagesStrategy

        monkeypatch.setenv("PARSE_STRATEGY", "topic")
        monkeypatch.setenv("PARSE_TOPIC_ID", "555")
        strategy = parsing.build_parsing_strategy()
        assert isinstance(strategy, TopicMessagesStrategy)
        assert strategy.topic_id == 555

    def test_unknown_name_raises(self, monkeypatch):
        monkeypatch.setenv("PARSE_STRATEGY", "nonsense")
        with pytest.raises(ValueError, match="PARSE_STRATEGY"):
            parsing.build_parsing_strategy()


class TestBuildUserFilterPipeline:
    def test_default_excludes_bots_only(self, monkeypatch):
        for var in (
            "PARSE_FILTER_LAST_SEEN_DAYS", "PARSE_FILTER_GENDER",
            "PARSE_FILTER_HAS_AVATAR", "PARSE_FILTER_PREMIUM",
        ):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.delenv("PARSE_FILTER_EXCLUDE_BOTS", raising=False)

        pipeline = parsing.build_user_filter_pipeline()

        assert pipeline.passes(ParsedUser(user_id=1, bot=False)) is True
        assert pipeline.passes(ParsedUser(user_id=2, bot=True)) is False

    def test_reads_all_filters(self, monkeypatch):
        monkeypatch.setenv("PARSE_FILTER_HAS_AVATAR", "1")
        monkeypatch.setenv("PARSE_FILTER_PREMIUM", "1")
        monkeypatch.setenv("PARSE_FILTER_EXCLUDE_BOTS", "0")
        monkeypatch.delenv("PARSE_FILTER_LAST_SEEN_DAYS", raising=False)
        monkeypatch.delenv("PARSE_FILTER_GENDER", raising=False)

        pipeline = parsing.build_user_filter_pipeline()

        matching = ParsedUser(user_id=1, has_photo=True, premium=True, bot=True)
        assert pipeline.passes(matching) is True
        assert pipeline.passes(ParsedUser(user_id=2, has_photo=False, premium=True, bot=True)) is False


class TestBuildJobKey:
    def test_unset_returns_none(self, monkeypatch):
        monkeypatch.delenv("PARSE_JOB_KEY", raising=False)
        assert parsing.build_job_key() is None

    def test_blank_returns_none(self, monkeypatch):
        monkeypatch.setenv("PARSE_JOB_KEY", "   ")
        assert parsing.build_job_key() is None

    def test_reads_and_trims(self, monkeypatch):
        monkeypatch.setenv("PARSE_JOB_KEY", "  my-job  ")
        assert parsing.build_job_key() == "my-job"


class TestProxyPreflight:
    async def test_disabled_by_default_returns_accounts_unchanged(self, monkeypatch):
        monkeypatch.delenv("PROXY_PREFLIGHT_CHECK_ENABLED", raising=False)
        accounts = [make_account("+1")]

        result = await parsing._proxy_preflight(accounts, logging.getLogger("test"))

        assert result == accounts

    async def test_warns_but_keeps_dead_proxy_accounts_by_default(self, monkeypatch, caplog):
        caplog.set_level(logging.WARNING)
        monkeypatch.setenv("PROXY_PREFLIGHT_CHECK_ENABLED", "1")
        monkeypatch.delenv("PROXY_PREFLIGHT_STRICT", raising=False)
        proxy = ProxyConfig(host="1.2.3.4", port=1080)
        accounts = [make_account("+1", proxy)]

        async def fake_check(accts, **kwargs):
            return {"+1": ProxyState(is_active=False, latency_ms=0.0, proxy_type=ProxyType.SOCKS5)}

        with patch("src.proxy.proxy_checker.check_account_proxies", side_effect=fake_check):
            result = await parsing._proxy_preflight(accounts, logging.getLogger("test"))

        assert result == accounts
        assert any("+1" in r.message for r in caplog.records)

    async def test_strict_excludes_dead_proxy_accounts(self, monkeypatch):
        monkeypatch.setenv("PROXY_PREFLIGHT_CHECK_ENABLED", "1")
        monkeypatch.setenv("PROXY_PREFLIGHT_STRICT", "1")
        proxy = ProxyConfig(host="1.2.3.4", port=1080)
        accounts = [make_account("+1", proxy), make_account("+2", None)]

        async def fake_check(accts, **kwargs):
            return {"+1": ProxyState(is_active=False, latency_ms=0.0, proxy_type=ProxyType.SOCKS5)}

        with patch("src.proxy.proxy_checker.check_account_proxies", side_effect=fake_check):
            result = await parsing._proxy_preflight(accounts, logging.getLogger("test"))

        assert [a.phone for a in result] == ["+2"]

    async def test_no_accounts_with_proxy_is_a_noop(self, monkeypatch):
        monkeypatch.setenv("PROXY_PREFLIGHT_CHECK_ENABLED", "1")
        accounts = [make_account("+1", None)]

        async def fake_check(accts, **kwargs):
            return {}

        with patch("src.proxy.proxy_checker.check_account_proxies", side_effect=fake_check):
            result = await parsing._proxy_preflight(accounts, logging.getLogger("test"))

        assert result == accounts


class TestRun:
    async def test_no_accounts_logs_error_and_returns(self, monkeypatch, caplog):
        caplog.set_level(logging.ERROR)
        monkeypatch.setattr(bootstrap, "load_accounts", lambda: ([], []))
        monkeypatch.setattr(bootstrap, "load_tdata_accounts", AsyncMock(return_value=[]))

        await parsing.run(None, logging.getLogger("test"))

        assert any("Аккаунты не найдены" in r.message for r in caplog.records)

    async def test_no_target_entity_logs_error(self, monkeypatch, caplog):
        caplog.set_level(logging.ERROR)
        monkeypatch.setattr(bootstrap, "load_accounts", lambda: ([make_account("+1")], []))
        monkeypatch.setattr(bootstrap, "load_tdata_accounts", AsyncMock(return_value=[]))
        monkeypatch.delenv("PARSE_ENTITIES", raising=False)
        monkeypatch.delenv("TG_TARGET_ENTITY", raising=False)
        monkeypatch.delenv("PROXY_PREFLIGHT_CHECK_ENABLED", raising=False)

        await parsing.run(None, logging.getLogger("test"))

        assert any("PARSE_ENTITIES" in r.message for r in caplog.records)

    async def test_uses_target_entity_when_parse_entities_unset(self, monkeypatch, tmp_path):
        monkeypatch.setattr(bootstrap, "load_accounts", lambda: ([make_account("+1")], []))
        monkeypatch.setattr(bootstrap, "load_tdata_accounts", AsyncMock(return_value=[]))
        monkeypatch.delenv("PROXY_PREFLIGHT_CHECK_ENABLED", raising=False)
        monkeypatch.setenv("TG_TARGET_ENTITY", "@fallback")
        monkeypatch.delenv("PARSE_ENTITIES", raising=False)
        monkeypatch.setenv("PARSE_EXPORT_MODE", "summary")
        monkeypatch.setenv("PARSE_EXPORT_PATH", str(tmp_path / "out.xlsx"))

        captured = {}

        async def fake_orchestrate(**kwargs):
            captured.update(kwargs)
            return DataExporter()

        with patch("src.orchestrator.orchestrate_extraction_only", new=AsyncMock(side_effect=fake_orchestrate)):
            await parsing.run(None, logging.getLogger("test"))

        assert captured["entity_identifiers"] == ["@fallback"]

    async def test_splits_parse_entities_on_comma(self, monkeypatch, tmp_path):
        monkeypatch.setattr(bootstrap, "load_accounts", lambda: ([make_account("+1")], []))
        monkeypatch.setattr(bootstrap, "load_tdata_accounts", AsyncMock(return_value=[]))
        monkeypatch.delenv("PROXY_PREFLIGHT_CHECK_ENABLED", raising=False)
        monkeypatch.setenv("TG_TARGET_ENTITY", "@fallback")
        monkeypatch.setenv("PARSE_ENTITIES", "@a, @b ,@c")
        monkeypatch.setenv("PARSE_EXPORT_MODE", "summary")
        monkeypatch.setenv("PARSE_EXPORT_PATH", str(tmp_path / "out.xlsx"))

        captured = {}

        async def fake_orchestrate(**kwargs):
            captured.update(kwargs)
            return DataExporter()

        with patch("src.orchestrator.orchestrate_extraction_only", new=AsyncMock(side_effect=fake_orchestrate)):
            await parsing.run(None, logging.getLogger("test"))

        assert captured["entity_identifiers"] == ["@a", "@b", "@c"]

    async def test_exports_by_source(self, monkeypatch, tmp_path):
        monkeypatch.setattr(bootstrap, "load_accounts", lambda: ([make_account("+1")], []))
        monkeypatch.setattr(bootstrap, "load_tdata_accounts", AsyncMock(return_value=[]))
        monkeypatch.delenv("PROXY_PREFLIGHT_CHECK_ENABLED", raising=False)
        monkeypatch.setenv("TG_TARGET_ENTITY", "@fallback")
        monkeypatch.setenv("PARSE_EXPORT_MODE", "by_source")
        out_dir = tmp_path / "by_source"
        monkeypatch.setenv("PARSE_EXPORT_PATH", str(out_dir))

        exporter = DataExporter()
        exporter.add(ParsedUser(user_id=1, username="alice", source="@fallback"))

        with patch("src.orchestrator.orchestrate_extraction_only", new=AsyncMock(return_value=exporter)):
            await parsing.run(None, logging.getLogger("test"))

        assert (out_dir / "_fallback.xlsx").exists()

    async def test_redis_dedup_disabled_by_default_passes_no_redis_client(self, monkeypatch, tmp_path):
        monkeypatch.setattr(bootstrap, "load_accounts", lambda: ([make_account("+1")], []))
        monkeypatch.setattr(bootstrap, "load_tdata_accounts", AsyncMock(return_value=[]))
        monkeypatch.delenv("PROXY_PREFLIGHT_CHECK_ENABLED", raising=False)
        monkeypatch.setenv("TG_TARGET_ENTITY", "@fallback")
        monkeypatch.delenv("PARSE_REDIS_DEDUP_ENABLED", raising=False)
        monkeypatch.setenv("PARSE_EXPORT_MODE", "summary")
        monkeypatch.setenv("PARSE_EXPORT_PATH", str(tmp_path / "out.xlsx"))

        captured = {}

        async def fake_orchestrate(**kwargs):
            captured.update(kwargs)
            return DataExporter()

        with patch("src.orchestrator.orchestrate_extraction_only", new=AsyncMock(side_effect=fake_orchestrate)):
            await parsing.run(None, logging.getLogger("test"))

        assert captured["redis_client"] is None

    async def test_redis_dedup_enabled_builds_and_closes_client(self, monkeypatch, tmp_path):
        monkeypatch.setattr(bootstrap, "load_accounts", lambda: ([make_account("+1")], []))
        monkeypatch.setattr(bootstrap, "load_tdata_accounts", AsyncMock(return_value=[]))
        monkeypatch.delenv("PROXY_PREFLIGHT_CHECK_ENABLED", raising=False)
        monkeypatch.setenv("TG_TARGET_ENTITY", "@fallback")
        monkeypatch.setenv("PARSE_REDIS_DEDUP_ENABLED", "1")
        monkeypatch.setenv("PARSE_JOB_KEY", "my-job")
        monkeypatch.setenv("PARSE_EXPORT_MODE", "summary")
        monkeypatch.setenv("PARSE_EXPORT_PATH", str(tmp_path / "out.xlsx"))

        fake_client = AsyncMock()
        captured = {}

        async def fake_orchestrate(**kwargs):
            captured.update(kwargs)
            return DataExporter()

        with (
            patch.object(bootstrap, "build_redis_client", return_value=fake_client),
            patch("src.orchestrator.orchestrate_extraction_only", new=AsyncMock(side_effect=fake_orchestrate)),
        ):
            await parsing.run(None, logging.getLogger("test"))

        assert captured["redis_client"] is fake_client
        assert captured["job_key"] == "my-job"
        fake_client.aclose.assert_awaited_once()
