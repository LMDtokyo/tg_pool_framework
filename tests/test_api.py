"""tests/test_api.py — FastAPI control API (src/api/app.py) consumed by the WPF launcher."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.config import AccountConfig, ProxyConfig
from src.messaging.messaging_service import BatchReport
from src.monitoring.event_bus import MetricUpdateEvent

pytestmark = pytest.mark.unit


def make_account(phone: str) -> AccountConfig:
    return AccountConfig(api_id=1, api_hash="h" * 32, phone=phone)


@pytest.fixture
def client(monkeypatch):
    accounts = [make_account("+7001"), make_account("+7002")]

    monkeypatch.setattr("src.bootstrap.load_accounts", lambda: (accounts, []))
    monkeypatch.setattr("src.bootstrap.load_tdata_accounts", AsyncMock(return_value=[]))
    monkeypatch.setattr("src.bootstrap.build_db_session_factory", lambda: None)
    monkeypatch.delenv("SESSION_ENCRYPTION_ENABLED", raising=False)

    from src.api.app import app
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
    from src.api.app import app

    accounts = [
        AccountConfig(
            api_id=1,
            api_hash="h" * 32,
            phone="+7001",
            proxy=ProxyConfig(host="1.2.3.4", port=1080, proxy_type="socks5"),
        ),
        make_account("+7002"),
    ]
    monkeypatch.setattr("src.bootstrap.load_accounts", lambda: (accounts, []))
    monkeypatch.setattr("src.bootstrap.load_tdata_accounts", AsyncMock(return_value=[]))
    monkeypatch.setattr("src.bootstrap.build_db_session_factory", lambda: None)
    monkeypatch.delenv("SESSION_ENCRYPTION_ENABLED", raising=False)

    with TestClient(app) as local_client:
        body = local_client.get("/accounts").json()

    by_phone = {account["phone"]: account for account in body}
    assert by_phone["+7001"]["uses_proxy"] is True
    assert by_phone["+7001"]["proxy_label"] == "1.2.3.4:1080"
    assert by_phone["+7002"]["uses_proxy"] is False
    assert by_phone["+7002"]["proxy_label"] is None


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
        "src.accounts.health_checker.ClientFactory.build", lambda account: mock_client
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
        "src.accounts.health_checker.ClientFactory.build", lambda account: mock_client
    )

    resp = client.post("/accounts/recheck", json={"deep": False})

    assert resp.status_code == 200
    assert resp.json()["unauthorized"] == 2
    accounts = client.get("/accounts", params={"status": "unauthorized"}).json()
    assert len(accounts) == 2
    assert {account["status"] for account in accounts} == {"unauthorized"}


def test_recheck_is_rejected_while_campaign_uses_account_pool(client, monkeypatch):
    monkeypatch.setattr(
        "src.api.campaign.orchestrate_multi_source",
        AsyncMock(side_effect=_fake_orchestrator(BatchReport())),
    )

    campaign_resp = client.post("/campaign/start", json={"target": "@test", "message": "hi"})
    assert campaign_resp.status_code == 200

    recheck_resp = client.post("/accounts/recheck", json={"deep": False})
    assert recheck_resp.status_code == 409
    assert "Account pool is busy" in recheck_resp.json()["detail"]

    client.post("/campaign/stop")


def test_startup_deduplicates_accounts_before_managers_receive_them(monkeypatch):
    from fastapi.testclient import TestClient
    from src.api.app import app

    captured = {}
    monkeypatch.setattr(
        "src.bootstrap.load_accounts",
        lambda: ([make_account("+7001")], []),
    )
    monkeypatch.setattr(
        "src.bootstrap.load_tdata_accounts",
        AsyncMock(return_value=[make_account("7001"), make_account("+7002")]),
    )
    monkeypatch.setattr("src.bootstrap.build_db_session_factory", lambda: None)
    monkeypatch.delenv("SESSION_ENCRYPTION_ENABLED", raising=False)

    async def fake_orchestrator(*, accounts, shutdown_event, event_bus, **kwargs):
        captured["phones"] = [account.phone for account in accounts]
        await shutdown_event.wait()
        return BatchReport()

    monkeypatch.setattr("src.api.campaign.orchestrate_multi_source", fake_orchestrator)

    with TestClient(app) as local_client:
        resp = local_client.post("/campaign/start", json={"target": "@test", "message": "hi"})
        assert resp.status_code == 200
        local_client.post("/campaign/stop")

    assert captured["phones"] == ["+7001", "+7002"]


def test_rescan_accounts_picks_up_newly_dropped_account(client, monkeypatch):
    monkeypatch.setattr(
        "src.bootstrap.load_accounts",
        lambda: ([make_account("+7001"), make_account("+7002"), make_account("+7003")], []),
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
        "src.bootstrap.load_accounts",
        lambda: ([make_account("+7001"), make_account("+7002")], [make_account("+7999")]),
    )

    resp = client.post("/accounts/rescan")
    assert resp.status_code == 200
    assert resp.json()["new_accounts"] == 1

    resp = client.get("/accounts")
    phones = {a["phone"] for a in resp.json()}
    assert "+7999" in phones


def _fake_orchestrator(report: BatchReport):
    """Publishes a MetricUpdateEvent, then blocks on shutdown_event like the real one."""
    async def _run(*, shutdown_event, event_bus, **kwargs):
        await event_bus.publish(MetricUpdateEvent(key="total_recipients", value=report.total))
        await shutdown_event.wait()
        return report
    return _run


def test_campaign_start_stop_status_lifecycle(client, monkeypatch):
    report = BatchReport(total=5, succeeded=4, failed=1)
    monkeypatch.setattr(
        "src.api.campaign.orchestrate_multi_source",
        AsyncMock(side_effect=_fake_orchestrator(report)),
    )

    resp = client.post("/campaign/start", json={"target": "@test", "message": "hi"})
    assert resp.status_code == 200
    campaign_id = resp.json()["campaign_id"]
    assert resp.json()["started"] is True

    resp = client.get("/campaign/status")
    body = resp.json()
    assert body["running"] is True
    assert body["campaign_id"] == campaign_id
    assert body["total"] == 5

    resp = client.post("/campaign/stop")
    assert resp.status_code == 200

    resp = client.get("/campaign/status")
    body = resp.json()
    assert body["running"] is False
    assert body["finished"] is True


def test_campaign_start_passes_new_payload_fields_through(client, monkeypatch):
    captured = {}

    async def fake_orchestrate(*, shutdown_event, event_bus, payload, **kwargs):
        captured["payload"] = payload
        await shutdown_event.wait()
        return BatchReport()

    monkeypatch.setattr(
        "src.api.campaign.orchestrate_multi_source", AsyncMock(side_effect=fake_orchestrate),
    )

    resp = client.post("/campaign/start", json={
        "target": "@test",
        "message": "{hi|hello}",
        "media_paths": ["a.jpg", "b.jpg"],
        "media_kind": "voice",
        "silent": True,
        "link_preview": False,
    })
    assert resp.status_code == 200

    client.post("/campaign/stop")

    payload = captured["payload"]
    assert payload.text == "{hi|hello}"
    assert payload.media_paths == ["a.jpg", "b.jpg"]
    assert payload.media_kind == "voice"
    assert payload.silent is True
    assert payload.link_preview is False


def test_campaign_start_passes_forward_fields_through(client, monkeypatch):
    captured = {}

    async def fake_orchestrate(*, shutdown_event, event_bus, payload, **kwargs):
        captured["payload"] = payload
        await shutdown_event.wait()
        return BatchReport()

    monkeypatch.setattr(
        "src.api.campaign.orchestrate_multi_source", AsyncMock(side_effect=fake_orchestrate),
    )

    resp = client.post("/campaign/start", json={
        "target": "@test",
        "message": "",
        "forward_link": "t.me/pythondev/123",
        "bot_relay_username": "postbot",
        "bot_relay_message_ids": [1, 2, 3],
    })
    assert resp.status_code == 200

    client.post("/campaign/stop")

    payload = captured["payload"]
    assert payload.forward_link == "t.me/pythondev/123"
    assert payload.bot_relay_username == "postbot"
    assert payload.bot_relay_message_ids == [1, 2, 3]


def test_campaign_start_with_account_folder_filters_accounts(client, monkeypatch):
    client.post("/accounts/+7001/folder", json={"value": "active"})
    # +7002 stays unfoldered.

    captured = {}

    async def fake_orchestrate(*, accounts, shutdown_event, event_bus, **kwargs):
        captured["accounts"] = accounts
        await shutdown_event.wait()
        return BatchReport()

    monkeypatch.setattr(
        "src.api.campaign.orchestrate_multi_source", AsyncMock(side_effect=fake_orchestrate),
    )

    resp = client.post("/campaign/start", json={
        "target": "@test", "message": "hi", "account_folder": "active",
    })
    assert resp.status_code == 200

    client.post("/campaign/stop")

    assert [a.phone for a in captured["accounts"]] == ["+7001"]


def test_campaign_start_with_account_folder_matching_nothing_returns_400(client):
    resp = client.post("/campaign/start", json={
        "target": "@test", "message": "hi", "account_folder": "nonexistent-folder",
    })
    assert resp.status_code == 400


def test_campaign_start_passes_messages_per_account_range_through(client, monkeypatch):
    captured = {}

    async def fake_orchestrate(*, shutdown_event, event_bus, **kwargs):
        captured.update(kwargs)
        await shutdown_event.wait()
        return BatchReport()

    monkeypatch.setattr(
        "src.api.campaign.orchestrate_multi_source", AsyncMock(side_effect=fake_orchestrate),
    )

    resp = client.post("/campaign/start", json={
        "target": "@test", "message": "hi",
        "messages_per_account_min": 3, "messages_per_account_max": 10,
    })
    assert resp.status_code == 200

    client.post("/campaign/stop")

    assert captured["messages_per_account_min"] == 3
    assert captured["messages_per_account_max"] == 10


def test_campaign_start_with_exact_total_target_uses_cycling_wrapper(client, monkeypatch):
    captured = {}

    async def fake_orchestrate_until_target(*, shutdown_event, event_bus, **kwargs):
        captured.update(kwargs)
        await shutdown_event.wait()
        return BatchReport()

    monkeypatch.setattr(
        "src.api.campaign.orchestrate_until_target",
        AsyncMock(side_effect=fake_orchestrate_until_target),
    )

    resp = client.post("/campaign/start", json={
        "target": "@test", "message": "hi", "exact_total_target": 50,
    })
    assert resp.status_code == 200

    client.post("/campaign/stop")

    assert captured["exact_total_target"] == 50


def test_campaign_start_without_exact_total_target_uses_plain_orchestrate(client, monkeypatch):
    plain_mock = AsyncMock(side_effect=_fake_orchestrator(BatchReport()))
    until_target_mock = AsyncMock()
    monkeypatch.setattr("src.api.campaign.orchestrate_multi_source", plain_mock)
    monkeypatch.setattr("src.api.campaign.orchestrate_until_target", until_target_mock)

    resp = client.post("/campaign/start", json={"target": "@test", "message": "hi"})
    assert resp.status_code == 200

    client.post("/campaign/stop")

    plain_mock.assert_called_once()
    until_target_mock.assert_not_called()


def test_campaign_start_passes_schedule_at_and_pin_after_send_in_payload(client, monkeypatch):
    captured_payload = {}

    async def fake_orchestrate(*, payload, shutdown_event, event_bus, **kwargs):
        captured_payload["payload"] = payload
        await shutdown_event.wait()
        return BatchReport()

    monkeypatch.setattr(
        "src.api.campaign.orchestrate_multi_source", AsyncMock(side_effect=fake_orchestrate),
    )

    resp = client.post("/campaign/start", json={
        "target": "@test", "message": "hi",
        "schedule_at": "2030-01-01T12:00:00", "pin_after_send": True,
    })
    assert resp.status_code == 200

    client.post("/campaign/stop")

    payload = captured_payload["payload"]
    assert payload.schedule_at.isoformat() == "2030-01-01T12:00:00"
    assert payload.pin_after_send is True


def test_campaign_start_passes_worker_batch_params_through(client, monkeypatch):
    captured = {}

    async def fake_orchestrate(*, shutdown_event, event_bus, **kwargs):
        captured.update(kwargs)
        await shutdown_event.wait()
        return BatchReport()

    monkeypatch.setattr(
        "src.api.campaign.orchestrate_multi_source", AsyncMock(side_effect=fake_orchestrate),
    )

    resp = client.post("/campaign/start", json={
        "target": "@test", "message": "hi",
        "worker_batch_size": 3, "worker_batch_delay_sec": 12.5,
    })
    assert resp.status_code == 200

    client.post("/campaign/stop")

    assert captured["worker_batch_size"] == 3
    assert captured["worker_batch_delay_sec"] == 12.5


def test_campaign_start_passes_repeat_every_hours_to_run_with_repeat(client, monkeypatch):
    captured = {}

    async def fake_run_with_repeat(run_once, shutdown_event, repeat_every_hours):
        captured["repeat_every_hours"] = repeat_every_hours
        return await run_once()

    monkeypatch.setattr(
        "src.api.campaign.orchestrate_multi_source", AsyncMock(return_value=BatchReport()),
    )
    monkeypatch.setattr("src.api.campaign.run_with_repeat", fake_run_with_repeat)

    resp = client.post("/campaign/start", json={
        "target": "@test", "message": "hi", "repeat_every_hours": 6.0,
    })
    assert resp.status_code == 200

    client.post("/campaign/stop")

    assert captured["repeat_every_hours"] == 6.0


def test_campaign_start_while_running_returns_409(client, monkeypatch):
    monkeypatch.setattr(
        "src.api.campaign.orchestrate_multi_source",
        AsyncMock(side_effect=_fake_orchestrator(BatchReport())),
    )

    first = client.post("/campaign/start", json={"target": "@test", "message": "hi"})
    assert first.status_code == 200

    second = client.post("/campaign/start", json={"target": "@other", "message": "hi"})
    assert second.status_code == 409

    client.post("/campaign/stop")


def test_campaign_status_when_nothing_started(client):
    resp = client.get("/campaign/status")
    assert resp.json() == {
        "running": False,
        "campaign_id": None,
        "target": None,
        "total": 0,
        "sent": 0,
        "failed": 0,
        "per_account": {},
        "finished": False,
        "error": None,
    }


def _fake_extraction(exporter_users):
    """Publishes a MetricUpdateEvent, then blocks on shutdown_event like the real one."""
    async def _run(*, shutdown_event, event_bus, **kwargs):
        from src.extraction.exporter import DataExporter
        exporter = DataExporter()
        exporter.add_many(exporter_users)
        await event_bus.publish(MetricUpdateEvent(key="total_recipients", value=len(exporter_users)))
        await shutdown_event.wait()
        return exporter
    return _run


def test_parsing_start_stop_status_lifecycle(client, monkeypatch):
    from src.extraction.data_extraction import ParsedUser

    users = {ParsedUser(user_id=1, username="alice", source="@test")}
    monkeypatch.setattr(
        "src.api.parsing.orchestrate_extraction_only",
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
        "src.api.parsing.orchestrate_extraction_only",
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


def test_parsing_redis_dedup_enabled_builds_and_passes_redis_client(client, monkeypatch):
    import src.bootstrap as bootstrap

    captured = {}

    async def fake_orchestrate(*, shutdown_event, event_bus, **kwargs):
        from src.extraction.exporter import DataExporter
        captured.update(kwargs)
        await shutdown_event.wait()
        return DataExporter()

    fake_client = AsyncMock()
    monkeypatch.setattr(bootstrap, "build_redis_client", lambda: fake_client)
    monkeypatch.setattr("src.api.parsing.orchestrate_extraction_only", AsyncMock(side_effect=fake_orchestrate))

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
        from src.extraction.exporter import DataExporter
        captured.update(kwargs)
        await shutdown_event.wait()
        return DataExporter()

    monkeypatch.setattr("src.api.parsing.orchestrate_extraction_only", AsyncMock(side_effect=fake_orchestrate))

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
        "sources": [], "export_path": None, "finished": False, "error": None,
    }


@pytest.mark.parametrize(
    ("mode", "filename", "method_name"),
    [
        ("full", "parsed_full.xlsx", "export_full"),
        ("summary", "parsed_summary.xlsx", "export_summary"),
    ],
)
def test_parsing_single_file_export_accepts_directory(tmp_path, mode, filename, method_name):
    from src.api.parsing import _export

    exporter = MagicMock()

    result = _export(exporter, mode, str(tmp_path))

    expected = tmp_path / filename
    assert result == expected
    getattr(exporter, method_name).assert_called_once_with(expected)


def test_parsing_full_export_preserves_explicit_filename(tmp_path):
    from src.api.parsing import _export

    exporter = MagicMock()
    output_path = tmp_path / "unity-members.xlsx"

    result = _export(exporter, "full", str(output_path))

    assert result == output_path
    exporter.export_full.assert_called_once_with(output_path)


def test_campaign_and_parsing_share_pool_guard(client, monkeypatch):
    """Regression: CampaignManager/ParsingManager share a ClientPool guard -- one running must reject (409) the other, not double-connect the same .session files."""
    monkeypatch.setattr(
        "src.api.campaign.orchestrate_multi_source",
        AsyncMock(side_effect=_fake_orchestrator(BatchReport())),
    )
    monkeypatch.setattr(
        "src.api.parsing.orchestrate_extraction_only",
        AsyncMock(side_effect=_fake_extraction(set())),
    )

    campaign_resp = client.post("/campaign/start", json={"target": "@test", "message": "hi"})
    assert campaign_resp.status_code == 200

    parsing_resp = client.post("/parsing/start", json={"entities": ["@test"]})
    assert parsing_resp.status_code == 409

    client.post("/campaign/stop")

    # Now that the campaign released the guard, parsing should be able to start.
    parsing_resp = client.post("/parsing/start", json={"entities": ["@test"]})
    assert parsing_resp.status_code == 200
    client.post("/parsing/stop")


def test_proxy_check_start_and_status_lifecycle(client, monkeypatch):
    from src.proxy.proxy_checker import ProxyState, ProxyType

    async def fake_check_all(proxies, *, concurrency=10):
        return [
            ProxyState(is_active=True, latency_ms=42.0, proxy_type=ProxyType.SOCKS5, country="RU"),
            ProxyState(is_active=False, latency_ms=0.0, proxy_type=ProxyType.HTTP, error_message="dead"),
        ]

    monkeypatch.setattr("src.api.proxy_check.check_all_proxies", AsyncMock(side_effect=fake_check_all))

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

    monkeypatch.setattr("src.api.proxy_check.check_all_proxies", AsyncMock(side_effect=fake_check_all))

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
    from src.api.app import app
    from src.db.proxy_repository import StoredProxy

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
    from src.api.app import app

    app.state.proxy_repository = None
    app.state.stored_proxy_check_manager = None

    assert client.get("/proxies").status_code == 503
    assert client.post("/proxies/check", json={}).status_code == 503


def test_dedicated_proxy_database_is_initialized_on_startup(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from src.api.app import app

    accounts = [make_account("+7001")]
    database_path = (tmp_path / "proxies.db").as_posix()
    monkeypatch.setattr("src.bootstrap.load_accounts", lambda: (accounts, []))
    monkeypatch.setattr("src.bootstrap.load_tdata_accounts", AsyncMock(return_value=[]))
    monkeypatch.setattr("src.bootstrap.build_db_session_factory", lambda: None)
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


def test_accounts_use_proxy_inventory_on_startup(monkeypatch, tmp_path):
    import sqlite3

    from fastapi.testclient import TestClient
    from src.api.app import app

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

    monkeypatch.setattr("src.bootstrap.load_accounts", lambda: (accounts, []))
    monkeypatch.setattr("src.bootstrap.load_tdata_accounts", AsyncMock(return_value=[]))
    monkeypatch.setattr("src.bootstrap.build_db_session_factory", lambda: None)
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
    from src.api.app import app

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

    monkeypatch.setattr("src.bootstrap.load_accounts", lambda: (accounts, []))
    monkeypatch.setattr("src.bootstrap.load_tdata_accounts", AsyncMock(return_value=[]))
    monkeypatch.setattr("src.bootstrap.build_db_session_factory", lambda: None)
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
    from src.api.app import app

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

    monkeypatch.setattr("src.bootstrap.load_accounts", lambda: (accounts, []))
    monkeypatch.setattr("src.bootstrap.load_tdata_accounts", AsyncMock(return_value=[]))
    monkeypatch.setattr("src.bootstrap.build_db_session_factory", lambda: None)
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
    from src.proxy.tdata_converter import ConversionResult

    tdata_dir = tmp_path / "tdata_root"
    tdata_dir.mkdir()

    monkeypatch.setattr(
        "src.api.tdata_convert.find_tdata_folders",
        lambda base: [str(tdata_dir / "acc1" / "tdata")],
    )

    async def fake_convert_batch(self, tdata_paths, output_dir, passwords=None, *, all_accounts=False):
        return [ConversionResult(source=tdata_paths[0], output="sessions/acc1.session", success=True)]

    monkeypatch.setattr(
        "src.api.tdata_convert.TDataConverter.convert_batch_tdata", fake_convert_batch,
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
    monkeypatch.setattr("src.api.tdata_convert.find_tdata_folders", lambda base: ["a", "b"])

    async def fake_convert_batch(self, tdata_paths, output_dir, passwords=None, *, all_accounts=False):
        await asyncio.sleep(0.2)
        return []

    monkeypatch.setattr(
        "src.api.tdata_convert.TDataConverter.convert_batch_tdata", fake_convert_batch,
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
    from src.proxy.tdata_converter import ConversionResult

    async def fake_convert_batch(self, session_configs, output_base_dir):
        return [
            ConversionResult(source=session_configs[0][0], output="tdata_out/acc1", success=True),
        ]

    monkeypatch.setattr(
        "src.api.session_convert.TDataConverter.convert_batch_sessions", fake_convert_batch,
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
        "src.api.session_convert.TDataConverter.convert_batch_sessions", fake_convert_batch,
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


def test_ws_events_receives_forwarded_metric_update(client, monkeypatch):
    """Regression: the WS handler must forward EventBus events without the queue/drain-task plumbing losing them."""
    report = BatchReport(total=7, succeeded=7, failed=0)
    monkeypatch.setattr(
        "src.api.campaign.orchestrate_multi_source",
        AsyncMock(side_effect=_fake_orchestrator(report)),
    )

    with client.websocket_connect("/ws/events") as ws:
        client.post("/campaign/start", json={"target": "@test", "message": "hi"})
        msg = ws.receive_json()
        assert msg["type"] == "MetricUpdateEvent"
        assert msg["data"] == {"key": "total_recipients", "value": 7}

    client.post("/campaign/stop")
