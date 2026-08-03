"""tests/test_license_gate.py — LicenseGateMiddleware wired into tg_pool/api/app.py."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from tg_pool.config import AccountConfig
from tg_pool.licensing.client import LicenseActivation

pytestmark = pytest.mark.unit


def _make_account(phone: str) -> AccountConfig:
    return AccountConfig(api_id=1, api_hash="h" * 32, phone=phone)


def _base_client(monkeypatch):
    monkeypatch.setattr("tg_pool.bootstrap.load_accounts", lambda **kwargs: ([_make_account("+7001")], []))
    monkeypatch.setattr("tg_pool.bootstrap.load_tdata_accounts", AsyncMock(return_value=[]))
    monkeypatch.setattr("tg_pool.bootstrap.build_db_session_factory", lambda: None)
    monkeypatch.delenv("SESSION_ENCRYPTION_ENABLED", raising=False)


def test_endpoints_are_open_when_licensing_is_not_configured(monkeypatch):
    _base_client(monkeypatch)
    monkeypatch.setenv("LICENSE_SERVER_URL", "")  # delenv would let load_dotenv() repopulate it from .env
    from tg_pool.api.app import app

    with TestClient(app) as client:
        assert client.get("/accounts").status_code == 200


def test_protected_endpoint_is_blocked_before_activation(monkeypatch):
    _base_client(monkeypatch)
    monkeypatch.setenv("LICENSE_SERVER_URL", "http://license.invalid")
    from tg_pool.api.app import app

    with TestClient(app) as client:
        response = client.get("/accounts")
    assert response.status_code == 402


def test_health_and_license_endpoints_stay_open_even_when_unlicensed(monkeypatch):
    _base_client(monkeypatch)
    monkeypatch.setenv("LICENSE_SERVER_URL", "http://license.invalid")
    from tg_pool.api.app import app

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/license/status").status_code == 200


def test_activating_unlocks_protected_endpoints(monkeypatch):
    _base_client(monkeypatch)
    monkeypatch.setenv("LICENSE_SERVER_URL", "http://license.invalid")
    monkeypatch.setattr(
        "tg_pool.licensing.client.LicenseServerClient.activate",
        AsyncMock(
            return_value=LicenseActivation(
                tier="month",
                activated_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            )
        ),
    )
    from tg_pool.api.app import app

    with TestClient(app) as client:
        blocked = client.get("/accounts")
        assert blocked.status_code == 402

        activated = client.post(
            "/license/activate", json={"license_key": "TGPL-AAAA-BBBB-CCCC-DDDD", "hwid": "hwid-1"}
        )
        assert activated.status_code == 200
        assert activated.json()["valid"] is True

        unlocked = client.get("/accounts")
        assert unlocked.status_code == 200


def test_failed_activation_reports_reason_and_stays_blocked(monkeypatch):
    _base_client(monkeypatch)
    monkeypatch.setenv("LICENSE_SERVER_URL", "http://license.invalid")
    from tg_pool.licensing.client import LicenseExpiredError

    monkeypatch.setattr(
        "tg_pool.licensing.client.LicenseServerClient.activate",
        AsyncMock(side_effect=LicenseExpiredError("expired")),
    )
    from tg_pool.api.app import app

    with TestClient(app) as client:
        response = client.post(
            "/license/activate", json={"license_key": "TGPL-AAAA-BBBB-CCCC-DDDD", "hwid": "hwid-1"}
        )
        assert response.status_code == 200  # the activate endpoint reports status, doesn't raise
        assert response.json()["valid"] is False
        assert response.json()["reason"] == "LicenseExpiredError"

        assert client.get("/accounts").status_code == 402
