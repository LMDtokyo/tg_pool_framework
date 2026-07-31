"""tests/test_scheduled_campaigns_api.py — /scheduled_campaigns HTTP layer, real DB persistence.

Unlike test_api.py's client fixture (which disables persistence entirely), this
wires a real in-memory SQLite database through bootstrap.build_db_session_factory()
so ScheduledCampaignManager is actually constructed and reachable over HTTP --
proving the app.py lifespan wiring itself, not just the manager in isolation
(already covered by tests/test_scheduled_campaigns.py).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from src.config import AccountConfig
from src.db.engine import build_session_factory

pytestmark = pytest.mark.unit


def make_account(phone: str) -> AccountConfig:
    return AccountConfig(api_id=1, api_hash="h" * 32, phone=phone)


@pytest.fixture
def client(monkeypatch, tmp_path):
    # A real file-backed SQLite DB, not :memory: -- SQLAlchemy's async pool can hand
    # out more than one physical connection across requests under TestClient's ASGI
    # dispatch, and an in-memory SQLite database is per-connection, so a second
    # connection sees an empty database. A temp file sidesteps that entirely and
    # matches how this app is actually deployed (DATABASE_URL points at a file).
    db_path = tmp_path / "scheduled_campaigns_test.db"
    accounts = [make_account("+7001")]

    monkeypatch.setattr("src.bootstrap.load_accounts", lambda **kwargs: (accounts, []))
    monkeypatch.setattr("src.bootstrap.load_tdata_accounts", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        "src.bootstrap.build_db_session_factory",
        lambda: build_session_factory(f"sqlite+aiosqlite:///{db_path}"),
    )
    monkeypatch.delenv("SESSION_ENCRYPTION_ENABLED", raising=False)
    monkeypatch.setenv("SCHEDULED_CAMPAIGNS_POLL_INTERVAL_SEC", "0.05")

    from src.api.app import app
    with TestClient(app) as c:
        yield c


def _future_iso(hours: float = 1.0) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def test_create_list_cancel_delete_roundtrip(client):
    created = client.post(
        "/scheduled_campaigns",
        json={
            "name": "Weekly promo",
            "campaign_type": "send_by_id",
            "send_by_id": {"database_path": "audience.txt", "message": "hi"},
            "start_at": _future_iso(),
            "repeat_interval_hours": 6,
            "max_occurrences": None,
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["name"] == "Weekly promo"
    assert body["campaign_type"] == "send_by_id"
    assert body["enabled"] is True
    assert body["occurrences_run"] == 0
    schedule_id = body["id"]

    listed = client.get("/scheduled_campaigns")
    assert listed.status_code == 200
    assert [c["id"] for c in listed.json()] == [schedule_id]

    cancelled = client.post(f"/scheduled_campaigns/{schedule_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["enabled"] is False

    deleted = client.delete(f"/scheduled_campaigns/{schedule_id}")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": 1}

    assert client.get("/scheduled_campaigns").json() == []
    assert client.delete(f"/scheduled_campaigns/{schedule_id}").status_code == 404


def test_create_send_by_numbers_campaign(client):
    resp = client.post(
        "/scheduled_campaigns",
        json={
            "name": "Numbers blast",
            "campaign_type": "send_by_numbers",
            "send_by_numbers": {"phone_numbers": ["+1555"], "message": "hi"},
            "start_at": _future_iso(),
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["campaign_type"] == "send_by_numbers"


def test_create_rejects_mismatched_payload(client):
    resp = client.post(
        "/scheduled_campaigns",
        json={
            "name": "Mismatched",
            "campaign_type": "send_by_numbers",
            "send_by_id": {"database_path": "audience.txt"},
            "start_at": _future_iso(),
        },
    )
    assert resp.status_code == 422


def test_create_rejects_start_at_in_the_past(client):
    resp = client.post(
        "/scheduled_campaigns",
        json={
            "name": "Too late",
            "campaign_type": "send_by_id",
            "send_by_id": {"database_path": "audience.txt"},
            "start_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
        },
    )
    assert resp.status_code == 400


def test_cancel_and_delete_unknown_schedule_return_404(client):
    assert client.post("/scheduled_campaigns/999999/cancel").status_code == 404
    assert client.delete("/scheduled_campaigns/999999").status_code == 404
