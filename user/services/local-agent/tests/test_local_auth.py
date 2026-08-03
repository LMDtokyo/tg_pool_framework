"""tests/test_local_auth.py — LocalAuthMiddleware wired into tg_pool/api/app.py."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from tg_pool.config import AccountConfig

pytestmark = pytest.mark.unit


def _make_account(phone: str) -> AccountConfig:
    return AccountConfig(api_id=1, api_hash="h" * 32, phone=phone)


def _base_client(monkeypatch):
    monkeypatch.setattr("tg_pool.bootstrap.load_accounts", lambda **kwargs: ([_make_account("+7001")], []))
    monkeypatch.setattr("tg_pool.bootstrap.load_tdata_accounts", AsyncMock(return_value=[]))
    monkeypatch.setattr("tg_pool.bootstrap.build_db_session_factory", lambda: None)
    monkeypatch.delenv("SESSION_ENCRYPTION_ENABLED", raising=False)
    monkeypatch.setenv("LICENSE_SERVER_URL", "")  # isolate from LicenseGateMiddleware


def test_endpoints_are_open_when_no_token_is_configured(monkeypatch):
    _base_client(monkeypatch)
    monkeypatch.setenv("LOCAL_API_TOKEN", "")
    from tg_pool.api.app import app

    with TestClient(app) as client:
        assert client.get("/accounts").status_code == 200


def test_endpoint_is_blocked_without_the_token_header(monkeypatch):
    _base_client(monkeypatch)
    monkeypatch.setenv("LOCAL_API_TOKEN", "secret-token")
    from tg_pool.api.app import app

    with TestClient(app) as client:
        response = client.get("/accounts")
    assert response.status_code == 401


def test_endpoint_is_blocked_with_the_wrong_token(monkeypatch):
    _base_client(monkeypatch)
    monkeypatch.setenv("LOCAL_API_TOKEN", "secret-token")
    from tg_pool.api.app import app

    with TestClient(app) as client:
        response = client.get("/accounts", headers={"X-Local-Token": "wrong-token"})
    assert response.status_code == 401


def test_endpoint_succeeds_with_the_correct_token(monkeypatch):
    _base_client(monkeypatch)
    monkeypatch.setenv("LOCAL_API_TOKEN", "secret-token")
    from tg_pool.api.app import app

    with TestClient(app) as client:
        response = client.get("/accounts", headers={"X-Local-Token": "secret-token"})
    assert response.status_code == 200


def test_health_stays_open_even_with_a_token_configured(monkeypatch):
    _base_client(monkeypatch)
    monkeypatch.setenv("LOCAL_API_TOKEN", "secret-token")
    from tg_pool.api.app import app

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
