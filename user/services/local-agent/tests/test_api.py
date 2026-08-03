"""tests/test_api.py — FastAPI control API (tg_pool/api/app.py) consumed by the WPF launcher."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from tg_pool.config import AccountConfig, ProxyConfig
from tg_pool.monitoring.event_bus import MetricUpdateEvent

pytestmark = pytest.mark.unit


def make_account(phone: str) -> AccountConfig:
    return AccountConfig(api_id=1, api_hash="h" * 32, phone=phone)


@pytest.fixture
def client(monkeypatch):
    accounts = [make_account("+7001"), make_account("+7002")]

    monkeypatch.setattr("tg_pool.bootstrap.load_accounts", lambda **kwargs: (accounts, []))
    monkeypatch.setattr("tg_pool.bootstrap.load_tdata_accounts", AsyncMock(return_value=[]))
    monkeypatch.setattr("tg_pool.bootstrap.build_db_session_factory", lambda: None)
    monkeypatch.delenv("SESSION_ENCRYPTION_ENABLED", raising=False)

    from tg_pool.api.app import app
    with TestClient(app) as c:
        yield c


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_list_accounts_returns_registered_accounts(client):
    resp = client.get("/accounts")
    assert resp.status_code == 200
    phones = {a["phone"] for a in resp.json()}
    assert phones == {"+7001", "+7002"}


def test_list_accounts_reports_configured_proxy(monkeypatch):
    from fastapi.testclient import TestClient
    from tg_pool.api.app import app

    accounts = [
        AccountConfig(
            api_id=1,
            api_hash="h" * 32,
            phone="+7001",
            proxy=ProxyConfig(host="1.2.3.4", port=1080, proxy_type="socks5"),
        ),
        make_account("+7002"),
    ]
    monkeypatch.setattr("tg_pool.bootstrap.load_accounts", lambda **kwargs: (accounts, []))
    monkeypatch.setattr("tg_pool.bootstrap.load_tdata_accounts", AsyncMock(return_value=[]))
    monkeypatch.setattr("tg_pool.bootstrap.build_db_session_factory", lambda: None)
    monkeypatch.delenv("SESSION_ENCRYPTION_ENABLED", raising=False)

    with TestClient(app) as local_client:
        body = local_client.get("/accounts").json()

    by_phone = {account["phone"]: account for account in body}
    assert by_phone["+7001"]["uses_proxy"] is True
    assert by_phone["+7001"]["proxy_label"] == "1.2.3.4:1080"
    assert by_phone["+7002"]["uses_proxy"] is False
    assert by_phone["+7002"]["proxy_label"] is None


def test_proxy_coverage_reports_unproxied_accounts(client):
    resp = client.get("/accounts/proxy_coverage")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_accounts"] == 2
    assert body["unproxied_count"] == 2
    assert set(body["unproxied_phones"]) == {"+7001", "+7002"}
    assert body["shared_proxy_group_count"] == 0


def test_proxy_coverage_detects_a_shared_exit(monkeypatch):
    from fastapi.testclient import TestClient
    from tg_pool.api.app import app

    shared_proxy = ProxyConfig(host="1.2.3.4", port=1080, proxy_type="socks5")
    accounts = [
        AccountConfig(api_id=1, api_hash="h" * 32, phone="+7001", proxy=shared_proxy),
        AccountConfig(api_id=1, api_hash="h" * 32, phone="+7002", proxy=shared_proxy),
        make_account("+7003"),
    ]
    monkeypatch.setattr("tg_pool.bootstrap.load_accounts", lambda **kwargs: (accounts, []))
    monkeypatch.setattr("tg_pool.bootstrap.load_tdata_accounts", AsyncMock(return_value=[]))
    monkeypatch.setattr("tg_pool.bootstrap.build_db_session_factory", lambda: None)
    monkeypatch.delenv("SESSION_ENCRYPTION_ENABLED", raising=False)

    with TestClient(app) as local_client:
        body = local_client.get("/accounts/proxy_coverage").json()

    assert body["total_accounts"] == 3
    assert body["unproxied_count"] == 1
    assert body["unproxied_phones"] == ["+7003"]
    assert body["shared_proxy_group_count"] == 1
    assert body["largest_shared_group_size"] == 2


def test_list_accounts_filters_by_text(client):
    resp = client.get("/accounts", params={"text": "+7001"})
    assert resp.status_code == 200
    phones = [a["phone"] for a in resp.json()]
    assert phones == ["+7001"]


def test_list_accounts_unknown_status_is_422(client):
    resp = client.get("/accounts", params={"status": "not-a-real-status"})
    assert resp.status_code == 422


def test_assign_role_persists(client):
    resp = client.post("/accounts/+7001/role", json={"value": "sender"})
    assert resp.status_code == 200

    resp = client.get("/accounts", params={"role": "sender"})
    phones = [a["phone"] for a in resp.json()]
    assert phones == ["+7001"]


def test_assign_folder_persists(client):
    resp = client.post("/accounts/+7001/folder", json={"value": "batch-1"})
    assert resp.status_code == 200

    resp = client.get("/accounts", params={"folder": "batch-1"})
    phones = [a["phone"] for a in resp.json()]
    assert phones == ["+7001"]


def test_recheck_updates_registry_status(client, monkeypatch):
    mock_client = AsyncMock()
    mock_client.connect = AsyncMock()
    mock_client.is_user_authorized = AsyncMock(return_value=True)
    mock_client.get_me = AsyncMock(return_value=MagicMock(premium=False, username="", first_name=""))
    mock_client.disconnect = AsyncMock()

    async def _dispatch(request):
        return MagicMock(has_password=False)

    mock_client.side_effect = _dispatch
    monkeypatch.setattr(
        "tg_pool.accounts.health_checker.ClientFactory.build", lambda account: mock_client
    )

    resp = client.post("/accounts/recheck", json={"deep": False})
    assert resp.status_code == 200
    body = resp.json()
    assert body["checked"] == 2
    assert body["alive"] == 2

    resp = client.get("/accounts", params={"status": "alive"})
    assert len(resp.json()) == 2


def test_recheck_reports_and_publishes_unauthorized_status(client, monkeypatch):
    mock_client = AsyncMock()
    mock_client.connect = AsyncMock()
    mock_client.is_user_authorized = AsyncMock(return_value=False)
    mock_client.disconnect = AsyncMock()
    monkeypatch.setattr(
        "tg_pool.accounts.health_checker.ClientFactory.build", lambda account: mock_client
    )

    resp = client.post("/accounts/recheck", json={"deep": False})

    assert resp.status_code == 200
    assert resp.json()["unauthorized"] == 2
    accounts = client.get("/accounts", params={"status": "unauthorized"}).json()
    assert len(accounts) == 2
    assert {account["status"] for account in accounts} == {"unauthorized"}


def test_startup_deduplicates_accounts_before_managers_receive_them(monkeypatch):
    from fastapi.testclient import TestClient
    from tg_pool.api.app import app

    monkeypatch.setattr(
        "tg_pool.bootstrap.load_accounts",
        lambda **kwargs: ([make_account("+7001")], []),
    )
    monkeypatch.setattr(
        "tg_pool.bootstrap.load_tdata_accounts",
        AsyncMock(return_value=[make_account("7001"), make_account("+7002")]),
    )
    monkeypatch.setattr("tg_pool.bootstrap.build_db_session_factory", lambda: None)
    monkeypatch.delenv("SESSION_ENCRYPTION_ENABLED", raising=False)

    with TestClient(app) as local_client:
        resp = local_client.get("/accounts")
        assert resp.status_code == 200

    assert [account["phone"] for account in resp.json()] == ["+7001", "+7002"]


def test_rescan_accounts_picks_up_newly_dropped_account(client, monkeypatch):
    monkeypatch.setattr(
        "tg_pool.bootstrap.load_accounts",
        lambda **kwargs: ([make_account("+7001"), make_account("+7002"), make_account("+7003")], []),
    )

    resp = client.post("/accounts/rescan")
    assert resp.status_code == 200
    assert resp.json()["new_accounts"] == 1

    resp = client.get("/accounts")
    phones = {a["phone"] for a in resp.json()}
    assert phones == {"+7001", "+7002", "+7003"}


def test_rescan_accounts_no_new_accounts_is_a_noop(client):
    resp = client.post("/accounts/rescan")
    assert resp.status_code == 200
    assert resp.json()["new_accounts"] == 0

    resp = client.get("/accounts")
    assert {a["phone"] for a in resp.json()} == {"+7001", "+7002"}


def test_rescan_accounts_also_finds_new_spares(client, monkeypatch):
    monkeypatch.setattr(
        "tg_pool.bootstrap.load_accounts",
        lambda **kwargs: ([make_account("+7001"), make_account("+7002")], [make_account("+7999")]),
    )

    resp = client.post("/accounts/rescan")
    assert resp.status_code == 200
    assert resp.json()["new_accounts"] == 1

    resp = client.get("/accounts")
    phones = {a["phone"] for a in resp.json()}
    assert "+7999" in phones


def test_rescan_accounts_reports_new_phones_and_failures(client, monkeypatch):
    monkeypatch.setattr(
        "tg_pool.bootstrap.load_accounts",
        lambda load_failures=None, **kwargs: (
            [make_account("+7001"), make_account("+7002"), make_account("+7003")],
            [],
        ),
    )
    monkeypatch.setattr(
        "tg_pool.bootstrap.load_tdata_accounts",
        AsyncMock(side_effect=lambda load_failures=None, **kwargs: (
            load_failures.append({"file": "broken_tdata", "reason": "invalid tdata folder"})
            if load_failures is not None else None
        ) or []),
    )

    resp = client.post("/accounts/rescan")
    assert resp.status_code == 200
    body = resp.json()
    assert body["new_phones"] == ["+7003"]
    assert body["failures"] == [{"file": "broken_tdata", "reason": "invalid tdata folder"}]


def test_send_by_id_manager_sees_accounts_registered_via_rescan(client, monkeypatch):
    monkeypatch.setattr(
        "tg_pool.bootstrap.load_accounts",
        lambda **kwargs: ([make_account("+7001"), make_account("+7002"), make_account("+7004")], []),
    )

    client.post("/accounts/rescan")

    from tg_pool.api.app import app as fastapi_app

    manager = fastapi_app.state.send_by_id_manager
    assert "7004" in manager._accounts_by_phone


def test_default_credentials_round_trip(client):
    resp = client.post(
        "/accounts/default_credentials", json={"api_id": 123456, "api_hash": "a" * 32}
    )
    assert resp.status_code == 200
    assert resp.json() == {"api_id": 123456, "api_hash": "a" * 32}

    resp = client.get("/accounts/default_credentials")
    assert resp.status_code == 200
    assert resp.json() == {"api_id": 123456, "api_hash": "a" * 32}


def test_default_credentials_rejects_a_malformed_hash(client):
    resp = client.post(
        "/accounts/default_credentials", json={"api_id": 123456, "api_hash": "not-hex"}
    )
    assert resp.status_code == 422


def _fake_extraction(exporter_users):
    """Publishes a MetricUpdateEvent, then blocks on shutdown_event like the real one."""
    async def _run(*, shutdown_event, event_bus, **kwargs):
        from tg_pool.extraction.exporter import DataExporter
        exporter = DataExporter()
        exporter.add_many(exporter_users)
        await event_bus.publish(MetricUpdateEvent(key="total_recipients", value=len(exporter_users)))
        await shutdown_event.wait()
        return exporter
    return _run


def test_parsing_start_stop_status_lifecycle(client, monkeypatch):
    from tg_pool.extraction.data_extraction import ParsedUser

    users = {ParsedUser(user_id=1, username="alice", source="@test")}
    monkeypatch.setattr(
        "tg_pool.api.parsing.orchestrate_extraction_only",
        AsyncMock(side_effect=_fake_extraction(users)),
    )

    resp = client.post("/parsing/start", json={"entities": ["@test"]})
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]
    assert resp.json()["started"] is True

    resp = client.get("/parsing/status")
    body = resp.json()
    assert body["running"] is True
    assert body["job_id"] == job_id
    assert body["total_collected"] == 1

    resp = client.post("/parsing/stop")
    assert resp.status_code == 200

    resp = client.get("/parsing/status")
    body = resp.json()
    assert body["running"] is False
    assert body["finished"] is True
    assert body["sources"] == ["@test"]


def test_parsing_start_while_running_returns_409(client, monkeypatch):
    monkeypatch.setattr(
        "tg_pool.api.parsing.orchestrate_extraction_only",
        AsyncMock(side_effect=_fake_extraction(set())),
    )

    first = client.post("/parsing/start", json={"entities": ["@test"]})
    assert first.status_code == 200

    second = client.post("/parsing/start", json={"entities": ["@other"]})
    assert second.status_code == 409

    client.post("/parsing/stop")


def test_parsing_unknown_strategy_returns_400(client):
    resp = client.post("/parsing/start", json={"entities": ["@test"], "strategy": "nonsense"})
    assert resp.status_code == 400


def test_parsing_auto_strategy_is_accepted(client, monkeypatch):
    captured = {}

    async def fake_orchestrate(*, strategy, strategy_selector, shutdown_event, event_bus, **kwargs):
        captured["strategy"] = strategy
        captured["strategy_selector"] = strategy_selector
        from tg_pool.extraction.exporter import DataExporter
        await shutdown_event.wait()
        return DataExporter()

    monkeypatch.setattr("tg_pool.api.parsing.orchestrate_extraction_only", AsyncMock(side_effect=fake_orchestrate))

    resp = client.post("/parsing/start", json={"entities": ["@test"], "strategy": "auto"})
    assert resp.status_code == 200

    client.post("/parsing/stop")

    assert captured["strategy"] is None
    from tg_pool.extraction.data_extraction import AutoStrategySelector
    assert isinstance(captured["strategy_selector"], AutoStrategySelector)


def _make_dialog(entity, title):
    dialog = MagicMock()
    dialog.entity = entity
    dialog.title = title
    return dialog


def test_parsing_sources_lists_groups_and_channels_skips_dms(client, monkeypatch):
    from telethon.tl.types import Channel, Chat, User

    supergroup = MagicMock()
    supergroup.__class__ = Channel
    supergroup.megagroup = True
    supergroup.username = "mygroup"
    supergroup.id = 111
    supergroup.participants_count = None

    channel = MagicMock()
    channel.__class__ = Channel
    channel.megagroup = False
    channel.username = None
    channel.id = 222
    channel.participants_count = None

    chat = MagicMock()
    chat.__class__ = Chat
    chat.username = None
    chat.id = 333
    chat.participants_count = 42

    dm_user = MagicMock()
    dm_user.__class__ = User

    dialogs = [
        _make_dialog(supergroup, "My Group"),
        _make_dialog(channel, "My Channel"),
        _make_dialog(chat, "Small Chat"),
        _make_dialog(dm_user, "Some Person"),
    ]

    async def fake_iter_dialogs(limit=200):
        for d in dialogs:
            yield d

    fake_client = AsyncMock()
    fake_client.is_user_authorized = AsyncMock(return_value=True)
    fake_client.iter_dialogs = fake_iter_dialogs
    fake_client.is_connected = MagicMock(return_value=True)

    monkeypatch.setattr(
        "tg_pool.accounts.connection_manager.ClientFactory.build",
        MagicMock(return_value=fake_client),
    )

    resp = client.get("/parsing/sources")
    assert resp.status_code == 200
    sources = resp.json()["sources"]

    assert len(sources) == 3  # the 1:1 dialog with dm_user is skipped
    by_identifier = {s["identifier"]: s for s in sources}
    assert by_identifier["@mygroup"]["kind"] == "supergroup"
    assert by_identifier["222"]["kind"] == "channel"
    assert by_identifier["333"]["kind"] == "chat"
    assert by_identifier["333"]["members_count"] == 42


def test_parsing_sources_conflicts_with_a_running_job(client, monkeypatch):
    monkeypatch.setattr(
        "tg_pool.api.parsing.orchestrate_extraction_only",
        AsyncMock(side_effect=_fake_extraction(set())),
    )
    assert client.post("/parsing/start", json={"entities": ["@test"]}).status_code == 200

    resp = client.get("/parsing/sources")
    assert resp.status_code == 409

    client.post("/parsing/stop")


def test_parsing_sources_unauthorized_account_returns_empty(client, monkeypatch):
    fake_client = AsyncMock()
    fake_client.is_user_authorized = AsyncMock(return_value=False)
    fake_client.is_connected = MagicMock(return_value=True)

    monkeypatch.setattr(
        "tg_pool.accounts.connection_manager.ClientFactory.build",
        MagicMock(return_value=fake_client),
    )

    resp = client.get("/parsing/sources")
    assert resp.status_code == 200
    assert resp.json()["sources"] == []


def test_parsing_redis_dedup_enabled_builds_and_passes_redis_client(client, monkeypatch):
    import tg_pool.bootstrap as bootstrap

    captured = {}

    async def fake_orchestrate(*, shutdown_event, event_bus, **kwargs):
        from tg_pool.extraction.exporter import DataExporter
        captured.update(kwargs)
        await shutdown_event.wait()
        return DataExporter()

    fake_client = AsyncMock()
    monkeypatch.setattr(bootstrap, "build_redis_client", lambda: fake_client)
    monkeypatch.setattr("tg_pool.api.parsing.orchestrate_extraction_only", AsyncMock(side_effect=fake_orchestrate))

    resp = client.post(
        "/parsing/start",
        json={"entities": ["@test"], "redis_dedup_enabled": True, "job_key": "job-42"},
    )
    assert resp.status_code == 200

    client.post("/parsing/stop")

    assert captured["redis_client"] is fake_client
    assert captured["job_key"] == "job-42"
    fake_client.aclose.assert_awaited_once()


def test_parsing_redis_dedup_disabled_by_default_passes_no_redis_client(client, monkeypatch):
    captured = {}

    async def fake_orchestrate(*, shutdown_event, event_bus, **kwargs):
        from tg_pool.extraction.exporter import DataExporter
        captured.update(kwargs)
        await shutdown_event.wait()
        return DataExporter()

    monkeypatch.setattr("tg_pool.api.parsing.orchestrate_extraction_only", AsyncMock(side_effect=fake_orchestrate))

    resp = client.post("/parsing/start", json={"entities": ["@test"]})
    assert resp.status_code == 200

    client.post("/parsing/stop")

    assert captured["redis_client"] is None
    assert captured["job_key"] is None


def test_parsing_topic_strategy_without_topic_id_returns_400(client):
    resp = client.post("/parsing/start", json={"entities": ["@test"], "strategy": "topic"})
    assert resp.status_code == 400


def test_parsing_status_when_nothing_started(client):
    resp = client.get("/parsing/status")
    assert resp.json() == {
        "running": False, "job_id": None, "entities": [], "total_collected": 0,
        "sources": [], "export_path": None, "db_path": None, "report_path": None,
        "txt_path": None, "accounts_used": 0, "stats": None, "finished": False, "error": None,
    }


def test_parsing_finish_populates_accounts_used_stats_db_and_report(client, monkeypatch, tmp_path):
    from pathlib import Path

    from tg_pool.extraction.data_extraction import ParsedUser
    from tg_pool.monitoring.event_bus import AccountStatusEvent

    users = {
        ParsedUser(user_id=1, username="alice", source="@test"),
        ParsedUser(user_id=2, phone="+79001234567", source="@test"),
    }

    async def fake_run(*, shutdown_event, event_bus, **kwargs):
        from tg_pool.extraction.exporter import DataExporter
        exporter = DataExporter()
        exporter.add_many(users)
        await event_bus.publish(AccountStatusEvent(phone="+1", status="alive", detail="pool ready"))
        await event_bus.publish(AccountStatusEvent(phone="+2", status="alive", detail="pool ready"))
        await shutdown_event.wait()
        return exporter

    monkeypatch.setattr("tg_pool.api.parsing.orchestrate_extraction_only", AsyncMock(side_effect=fake_run))

    resp = client.post(
        "/parsing/start",
        json={"entities": ["@test"], "export_path": str(tmp_path / "out.xlsx")},
    )
    assert resp.status_code == 200

    client.post("/parsing/stop")

    status = client.get("/parsing/status").json()
    assert status["accounts_used"] == 2
    assert status["stats"] == {
        "total": 2, "with_username": 1, "without_username": 1,
        "with_phone": 1, "premium": 0, "bots": 0,
    }
    assert status["db_path"] is not None
    assert Path(status["db_path"]).exists()
    assert status["txt_path"] is not None
    assert Path(status["txt_path"]).exists()
    assert status["report_path"] is not None
    # utf-16, not utf-8: Windows' classic console `type` renders this without
    # mojibake (see tg_pool.api.parsing._write_report).
    report_text = Path(status["report_path"]).read_text(encoding="utf-16")
    assert "Задействовано аккаунтов: 2" in report_text
    assert "Собрано пользователей:   2" in report_text

    # Regression: db/txt/report used to be able to collide onto the same
    # filename (independently-recomputed same-second timestamps), and
    # whichever wrote last clobbered the others -- e.g. the report silently
    # overwriting the real user list that Send by ID reads as a database.
    db_path, txt_path, report_path = (
        Path(status["db_path"]), Path(status["txt_path"]), Path(status["report_path"]),
    )
    assert len({db_path, txt_path, report_path}) == 3
    assert db_path.parent == txt_path.parent == report_path.parent

    audience_text = txt_path.read_text(encoding="utf-8-sig")
    assert "@alice" in audience_text
    assert "+79001234567" in audience_text
    assert "ОТЧЁТ ПАРСИНГА" not in audience_text


def test_parsing_report_follows_the_requested_language(client, monkeypatch, tmp_path):
    import re
    from pathlib import Path

    from tg_pool.extraction.data_extraction import ParsedUser

    async def fake_run(*, shutdown_event, event_bus, **kwargs):
        from tg_pool.extraction.exporter import DataExporter
        exporter = DataExporter()
        exporter.add(ParsedUser(user_id=1, username="alice", source="@test"))
        await shutdown_event.wait()
        return exporter

    monkeypatch.setattr("tg_pool.api.parsing.orchestrate_extraction_only", AsyncMock(side_effect=fake_run))

    resp = client.post(
        "/parsing/start",
        json={"entities": ["@test"], "export_path": str(tmp_path / "out.xlsx"), "language": "en"},
    )
    assert resp.status_code == 200

    client.post("/parsing/stop")

    status = client.get("/parsing/status").json()
    report_text = Path(status["report_path"]).read_text(encoding="utf-16")
    assert "PARSING REPORT" in report_text
    assert re.search(r"Accounts used:\s+0", report_text)
    assert re.search(r"Users collected:\s+1", report_text)
    assert "ОТЧЁТ ПАРСИНГА" not in report_text


@pytest.mark.parametrize(
    ("mode", "filename", "method_name"),
    [
        ("full", "parsed_full.xlsx", "export_full"),
        ("summary", "parsed_summary.xlsx", "export_summary"),
    ],
)
def test_parsing_single_file_export_accepts_directory(tmp_path, mode, filename, method_name):
    from tg_pool.api.parsing import _export

    exporter = MagicMock()

    result = _export(exporter, mode, str(tmp_path))

    expected = tmp_path / filename
    assert result == expected
    getattr(exporter, method_name).assert_called_once_with(expected)


def test_parsing_full_export_preserves_explicit_filename(tmp_path):
    from tg_pool.api.parsing import _export

    exporter = MagicMock()
    output_path = tmp_path / "unity-members.xlsx"

    result = _export(exporter, "full", str(output_path))

    assert result == output_path
    exporter.export_full.assert_called_once_with(output_path)


def test_proxy_check_start_and_status_lifecycle(client, monkeypatch):
    from tg_pool.proxy.proxy_checker import ProxyState, ProxyType

    async def fake_check_all(proxies, *, concurrency=10):
        return [
            ProxyState(is_active=True, latency_ms=42.0, proxy_type=ProxyType.SOCKS5, country="RU"),
            ProxyState(is_active=False, latency_ms=0.0, proxy_type=ProxyType.HTTP, error_message="dead"),
        ]

    monkeypatch.setattr("tg_pool.api.proxy_check.check_all_proxies", AsyncMock(side_effect=fake_check_all))

    resp = client.post("/proxy_check/start", json={
        "proxies": [
            {"type": "socks5", "host": "1.2.3.4", "port": 1080},
            {"type": "http", "host": "5.6.7.8", "port": 8080},
        ],
    })
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]
    assert resp.json()["started"] is True

    resp = client.get("/proxy_check/status")
    body = resp.json()
    assert body["job_id"] == job_id
    assert body["finished"] is True
    assert body["total"] == 2
    assert body["results"][0] == {
        "host": "1.2.3.4", "port": 1080, "proxy_type": "socks5",
        "is_active": True, "latency_ms": 42.0, "error_message": None, "country": "RU",
    }
    assert body["results"][1]["is_active"] is False
    assert body["results"][1]["error_message"] == "dead"


def test_proxy_check_start_while_running_returns_409(client, monkeypatch):
    async def fake_check_all(proxies, *, concurrency=10):
        await asyncio.sleep(0.2)
        return []

    monkeypatch.setattr("tg_pool.api.proxy_check.check_all_proxies", AsyncMock(side_effect=fake_check_all))

    first = client.post("/proxy_check/start", json={"proxies": [{"host": "1.2.3.4", "port": 1080}]})
    assert first.status_code == 200

    second = client.post("/proxy_check/start", json={"proxies": [{"host": "5.6.7.8", "port": 8080}]})
    assert second.status_code == 409


def test_proxy_check_status_when_nothing_started(client):
    resp = client.get("/proxy_check/status")
    assert resp.json() == {
        "running": False, "job_id": None, "total": 0, "results": [], "finished": False, "error": None,
    }


def test_proxy_check_requires_at_least_one_proxy(client):
    resp = client.post("/proxy_check/start", json={"proxies": []})
    assert resp.status_code == 422


def test_stored_proxy_api_add_list_check_and_delete(client):
    from tg_pool.api.app import app
    from tg_pool.db.proxy_repository import StoredProxy

    stored = StoredProxy(
        id=7,
        proxy_type="http",
        host="1.2.3.4",
        port=8080,
        username="user",
        password="pass",
        version="ipv4",
        status="unknown",
        response_ms=None,
        country=None,
        error_message=None,
        last_checked_at=None,
        ban_signal_count=0,
        last_ban_signal_at=None,
    )
    repository = MagicMock()
    repository.list_all = AsyncMock(return_value=[stored])
    repository.upsert_many = AsyncMock(return_value=1)
    repository.delete_one = AsyncMock(return_value=True)
    repository.delete_bad = AsyncMock(return_value=2)
    repository.delete_all = AsyncMock(return_value=3)
    manager = MagicMock()
    manager.start.return_value = "stored-job"
    manager.stop = AsyncMock()
    manager.status.return_value = {
        "running": False,
        "job_id": "stored-job",
        "total": 1,
        "completed": 1,
        "finished": True,
        "error": None,
    }
    app.state.proxy_repository = repository
    app.state.stored_proxy_check_manager = manager

    response = client.post(
        "/proxies",
        json={"protocol": "http", "proxy_list": "1.2.3.4:8080:user:pass"},
    )
    assert response.status_code == 200
    assert response.json()[0]["status"] == "unknown"
    repository.upsert_many.assert_awaited_once_with(
        [
            {
                "proxy_type": "http",
                "host": "1.2.3.4",
                "port": 8080,
                "username": "user",
                "password": "pass",
            }
        ]
    )

    response = client.post(
        "/proxies/check",
        json={"proxy_ids": [7], "timeout": 45, "retries": 15},
    )
    assert response.json() == {"job_id": "stored-job", "started": True}
    manager.start.assert_called_once_with(
        [7], concurrency=10, timeout=45.0, retries=15, retry_delay=0.5
    )
    assert client.get("/proxies/check/status").json()["completed"] == 1

    assert client.delete("/proxies/7").json() == {"deleted": 1}
    assert client.delete("/proxies/bad").json() == {"deleted": 2}
    assert client.delete("/proxies").json() == {"deleted": 3}


def test_stored_proxy_api_requires_database(client):
    from tg_pool.api.app import app

    app.state.proxy_repository = None
    app.state.stored_proxy_check_manager = None

    assert client.get("/proxies").status_code == 503
    assert client.post("/proxies/check", json={}).status_code == 503


def test_dedicated_proxy_database_is_initialized_on_startup(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from tg_pool.api.app import app

    accounts = [make_account("+7001")]
    database_path = (tmp_path / "proxies.db").as_posix()
    monkeypatch.setattr("tg_pool.bootstrap.load_accounts", lambda **kwargs: (accounts, []))
    monkeypatch.setattr("tg_pool.bootstrap.load_tdata_accounts", AsyncMock(return_value=[]))
    monkeypatch.setattr("tg_pool.bootstrap.build_db_session_factory", lambda: None)
    monkeypatch.setenv("PROXY_DATABASE_URL", f"sqlite+aiosqlite:///{database_path}")
    monkeypatch.delenv("SESSION_ENCRYPTION_ENABLED", raising=False)

    with TestClient(app) as local_client:
        assert local_client.get("/proxies").json() == []
        response = local_client.post(
            "/proxies",
            json={"protocol": "socks5", "proxy_list": "1.2.3.4:1080:user:pass"},
        )
        assert response.status_code == 200
        assert response.json()[0]["host"] == "1.2.3.4"

    assert (tmp_path / "proxies.db").exists()


def test_local_account_database_is_initialized_on_startup(monkeypatch, tmp_path):
    import sqlite3

    from fastapi.testclient import TestClient
    from tg_pool.api.app import app

    accounts = [make_account("+7001")]
    database_path = tmp_path / "accounts.db"
    monkeypatch.setattr("tg_pool.bootstrap.load_accounts", lambda **kwargs: (accounts, []))
    monkeypatch.setattr("tg_pool.bootstrap.load_tdata_accounts", AsyncMock(return_value=[]))
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("ACCOUNT_DATABASE_URL", f"sqlite+aiosqlite:///{database_path.as_posix()}")
    monkeypatch.delenv("PROXY_DATABASE_URL", raising=False)
    monkeypatch.delenv("SESSION_ENCRYPTION_ENABLED", raising=False)

    with TestClient(app) as local_client:
        assert local_client.get("/accounts").json()[0]["phone"] == "+7001"

    with sqlite3.connect(database_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]

    assert count == 1


def test_accounts_use_proxy_inventory_on_startup(monkeypatch, tmp_path):
    import sqlite3

    from fastapi.testclient import TestClient
    from tg_pool.api.app import app

    accounts = [make_account("+7001")]
    database_path = tmp_path / "proxies.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE proxies (
                id INTEGER PRIMARY KEY,
                proxy_type TEXT NOT NULL DEFAULT 'socks5',
                host TEXT NOT NULL,
                port INTEGER NOT NULL,
                username TEXT NOT NULL DEFAULT '',
                password TEXT NOT NULL DEFAULT '',
                version TEXT NOT NULL DEFAULT 'ipv4',
                status TEXT NOT NULL DEFAULT 'unknown',
                response_ms FLOAT NULL,
                country TEXT NULL,
                error_message TEXT NULL,
                last_checked_at DATETIME NULL,
                ban_signal_count INTEGER NOT NULL DEFAULT 0,
                last_ban_signal_at DATETIME NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_proxies_endpoint_user UNIQUE (proxy_type, host, port, username)
            )
            """
        )
        connection.execute(
            """
            INSERT INTO proxies (proxy_type, host, port, username, password)
            VALUES ('http', '9.8.7.6', 9200, 'proxy-user', 'proxy-pass')
            """
        )

    monkeypatch.setattr("tg_pool.bootstrap.load_accounts", lambda **kwargs: (accounts, []))
    monkeypatch.setattr("tg_pool.bootstrap.load_tdata_accounts", AsyncMock(return_value=[]))
    monkeypatch.setattr("tg_pool.bootstrap.build_db_session_factory", lambda: None)
    monkeypatch.setenv("PROXY_DATABASE_URL", f"sqlite+aiosqlite:///{database_path.as_posix()}")
    monkeypatch.delenv("SESSION_ENCRYPTION_ENABLED", raising=False)

    with TestClient(app) as local_client:
        response = local_client.get("/accounts")

    assert response.status_code == 200
    assert response.json()[0]["uses_proxy"] is True
    assert response.json()[0]["proxy_label"] == "9.8.7.6:9200"
    assert response.json()[0]["proxy_status"] == "unknown"


def test_accounts_report_bad_stored_proxy_status(monkeypatch, tmp_path):
    import sqlite3

    from fastapi.testclient import TestClient
    from tg_pool.api.app import app

    accounts = [make_account("+7001")]
    database_path = tmp_path / "proxies.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE proxies (
                id INTEGER PRIMARY KEY,
                proxy_type TEXT NOT NULL DEFAULT 'socks5',
                host TEXT NOT NULL,
                port INTEGER NOT NULL,
                username TEXT NOT NULL DEFAULT '',
                password TEXT NOT NULL DEFAULT '',
                version TEXT NOT NULL DEFAULT 'ipv4',
                status TEXT NOT NULL DEFAULT 'unknown',
                response_ms FLOAT NULL,
                country TEXT NULL,
                error_message TEXT NULL,
                last_checked_at DATETIME NULL,
                ban_signal_count INTEGER NOT NULL DEFAULT 0,
                last_ban_signal_at DATETIME NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_proxies_endpoint_user UNIQUE (proxy_type, host, port, username)
            )
            """
        )
        connection.execute(
            """
            INSERT INTO proxies (proxy_type, host, port, username, password, status)
            VALUES ('socks5', '9.8.7.6', 9200, 'proxy-user', 'proxy-pass', 'bad')
            """
        )

    monkeypatch.setattr("tg_pool.bootstrap.load_accounts", lambda **kwargs: (accounts, []))
    monkeypatch.setattr("tg_pool.bootstrap.load_tdata_accounts", AsyncMock(return_value=[]))
    monkeypatch.setattr("tg_pool.bootstrap.build_db_session_factory", lambda: None)
    monkeypatch.setenv("PROXY_DATABASE_URL", f"sqlite+aiosqlite:///{database_path.as_posix()}")
    monkeypatch.delenv("SESSION_ENCRYPTION_ENABLED", raising=False)

    with TestClient(app) as local_client:
        response = local_client.get("/accounts")

    assert response.status_code == 200
    assert response.json()[0]["proxy_label"] == "9.8.7.6:9200"
    assert response.json()[0]["proxy_status"] == "bad"


def test_deleting_assigned_proxy_reassigns_account_to_remaining_proxy(monkeypatch, tmp_path):
    import sqlite3

    from fastapi.testclient import TestClient
    from tg_pool.api.app import app

    accounts = [make_account("+7001")]
    database_path = tmp_path / "proxies.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE proxies (
                id INTEGER PRIMARY KEY,
                proxy_type TEXT NOT NULL DEFAULT 'socks5',
                host TEXT NOT NULL,
                port INTEGER NOT NULL,
                username TEXT NOT NULL DEFAULT '',
                password TEXT NOT NULL DEFAULT '',
                version TEXT NOT NULL DEFAULT 'ipv4',
                status TEXT NOT NULL DEFAULT 'unknown',
                response_ms FLOAT NULL,
                country TEXT NULL,
                error_message TEXT NULL,
                last_checked_at DATETIME NULL,
                ban_signal_count INTEGER NOT NULL DEFAULT 0,
                last_ban_signal_at DATETIME NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_proxies_endpoint_user UNIQUE (proxy_type, host, port, username)
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO proxies (id, proxy_type, host, port, username, password, status)
            VALUES (?, 'socks5', ?, ?, '', '', 'ok')
            """,
            [
                (1, "1.1.1.1", 1001),
                (2, "2.2.2.2", 2002),
            ],
        )

    monkeypatch.setattr("tg_pool.bootstrap.load_accounts", lambda **kwargs: (accounts, []))
    monkeypatch.setattr("tg_pool.bootstrap.load_tdata_accounts", AsyncMock(return_value=[]))
    monkeypatch.setattr("tg_pool.bootstrap.build_db_session_factory", lambda: None)
    monkeypatch.setenv("PROXY_DATABASE_URL", f"sqlite+aiosqlite:///{database_path.as_posix()}")
    monkeypatch.delenv("SESSION_ENCRYPTION_ENABLED", raising=False)

    with TestClient(app) as local_client:
        assert local_client.get("/accounts").json()[0]["proxy_label"] == "1.1.1.1:1001"
        delete_response = local_client.delete("/proxies/1")
        account_response = local_client.get("/accounts")

    assert delete_response.status_code == 200
    assert account_response.json()[0]["uses_proxy"] is True
    assert account_response.json()[0]["proxy_label"] == "2.2.2.2:2002"


def test_tdata_convert_start_and_status_lifecycle(client, monkeypatch, tmp_path):
    from tg_pool.proxy.tdata_converter import ConversionResult

    tdata_dir = tmp_path / "tdata_root"
    tdata_dir.mkdir()

    monkeypatch.setattr(
        "tg_pool.api.tdata_convert.find_tdata_folders",
        lambda base: [str(tdata_dir / "acc1" / "tdata")],
    )

    async def fake_convert_batch(self, tdata_paths, output_dir, passwords=None, *, all_accounts=False):
        return [ConversionResult(source=tdata_paths[0], output="sessions/acc1.session", success=True)]

    monkeypatch.setattr(
        "tg_pool.api.tdata_convert.TDataConverter.convert_batch_tdata", fake_convert_batch,
    )

    resp = client.post("/tdata_convert/start", json={"tdata_dir": str(tdata_dir)})
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]
    assert resp.json()["started"] is True

    resp = client.get("/tdata_convert/status")
    body = resp.json()
    assert body["job_id"] == job_id
    assert body["finished"] is True
    assert body["total"] == 1
    assert body["results"] == [{
        "source": str(tdata_dir / "acc1" / "tdata"), "output": "sessions/acc1.session",
        "success": True, "error": "",
    }]


def test_tdata_convert_nonexistent_dir_returns_400(client):
    resp = client.post("/tdata_convert/start", json={"tdata_dir": "/no/such/path/at/all"})
    assert resp.status_code == 400


def test_tdata_convert_empty_dir_returns_400(client, tmp_path):
    resp = client.post("/tdata_convert/start", json={"tdata_dir": str(tmp_path)})
    assert resp.status_code == 400
    assert "No valid tdata folders" in resp.json()["detail"]


def test_tdata_convert_start_while_running_returns_409(client, monkeypatch, tmp_path):
    tdata_dir = tmp_path / "tdata_root"
    tdata_dir.mkdir()
    monkeypatch.setattr("tg_pool.api.tdata_convert.find_tdata_folders", lambda base: ["a", "b"])

    async def fake_convert_batch(self, tdata_paths, output_dir, passwords=None, *, all_accounts=False):
        await asyncio.sleep(0.2)
        return []

    monkeypatch.setattr(
        "tg_pool.api.tdata_convert.TDataConverter.convert_batch_tdata", fake_convert_batch,
    )

    first = client.post("/tdata_convert/start", json={"tdata_dir": str(tdata_dir)})
    assert first.status_code == 200

    second = client.post("/tdata_convert/start", json={"tdata_dir": str(tdata_dir)})
    assert second.status_code == 409


def test_tdata_convert_status_when_nothing_started(client):
    resp = client.get("/tdata_convert/status")
    assert resp.json() == {
        "running": False, "job_id": None, "total": 0, "results": [], "finished": False, "error": None,
    }


def test_session_convert_start_and_status_lifecycle(client, monkeypatch):
    from tg_pool.proxy.tdata_converter import ConversionResult

    async def fake_convert_batch(self, session_configs, output_base_dir):
        return [
            ConversionResult(source=session_configs[0][0], output="tdata_out/acc1", success=True),
        ]

    monkeypatch.setattr(
        "tg_pool.api.session_convert.TDataConverter.convert_batch_sessions", fake_convert_batch,
    )

    resp = client.post("/session_convert/start", json={
        "items": [{"session_path": "s.session", "json_path": "s.json", "output_subdir": "acc1"}],
    })
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]
    assert resp.json()["started"] is True

    resp = client.get("/session_convert/status")
    body = resp.json()
    assert body["job_id"] == job_id
    assert body["finished"] is True
    assert body["total"] == 1
    assert body["results"] == [{
        "source": "s.session", "output": "tdata_out/acc1", "success": True, "error": "",
    }]


def test_session_convert_start_while_running_returns_409(client, monkeypatch):
    async def fake_convert_batch(self, session_configs, output_base_dir):
        await asyncio.sleep(0.2)
        return []

    monkeypatch.setattr(
        "tg_pool.api.session_convert.TDataConverter.convert_batch_sessions", fake_convert_batch,
    )

    item = {"session_path": "s.session", "json_path": "s.json", "output_subdir": "acc1"}
    first = client.post("/session_convert/start", json={"items": [item]})
    assert first.status_code == 200

    second = client.post("/session_convert/start", json={"items": [item]})
    assert second.status_code == 409


def test_session_convert_status_when_nothing_started(client):
    resp = client.get("/session_convert/status")
    assert resp.json() == {
        "running": False, "job_id": None, "total": 0, "results": [], "finished": False, "error": None,
    }


def test_session_convert_requires_at_least_one_item(client):
    resp = client.post("/session_convert/start", json={"items": []})
    assert resp.status_code == 422


