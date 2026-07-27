from fastapi.testclient import TestClient

from license_server.app import app

_ADMIN_KEY = "test-admin-key"


def _client(monkeypatch, tmp_path):
    db_path = (tmp_path / "license.db").as_posix()
    monkeypatch.setenv("LICENSE_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("LICENSE_ADMIN_API_KEY", _ADMIN_KEY)
    return TestClient(app)


def test_admin_endpoint_rejects_missing_key(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        response = client.post("/admin/keys", json={"tier": "month", "count": 1})
    assert response.status_code == 401


def test_admin_endpoint_rejects_wrong_key(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        response = client.post(
            "/admin/keys",
            json={"tier": "month", "count": 1},
            headers={"X-Admin-Key": "wrong"},
        )
    assert response.status_code == 401


def test_generate_then_activate_round_trip(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        generated = client.post(
            "/admin/keys",
            json={"tier": "month", "count": 1, "note": "test order"},
            headers={"X-Admin-Key": _ADMIN_KEY},
        )
        assert generated.status_code == 200
        key_code = generated.json()["keys"][0]["key_code"]

        activated = client.post(
            "/license/activate",
            json={"license_key": key_code, "hwid": "machine-a-hardware-uuid"},
        )
        assert activated.status_code == 200
        body = activated.json()
        assert body["tier"] == "month"
        assert body["expires_at"] > body["activated_at"]


def test_activate_same_device_twice_succeeds(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        key_code = client.post(
            "/admin/keys",
            json={"tier": "week", "count": 1},
            headers={"X-Admin-Key": _ADMIN_KEY},
        ).json()["keys"][0]["key_code"]

        first = client.post("/license/activate", json={"license_key": key_code, "hwid": "hw-1"})
        second = client.post("/license/activate", json={"license_key": key_code, "hwid": "hw-1"})

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["expires_at"] == second.json()["expires_at"]


def test_activate_from_second_device_is_conflict(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        key_code = client.post(
            "/admin/keys",
            json={"tier": "week", "count": 1},
            headers={"X-Admin-Key": _ADMIN_KEY},
        ).json()["keys"][0]["key_code"]

        client.post("/license/activate", json={"license_key": key_code, "hwid": "hw-1"})
        response = client.post("/license/activate", json={"license_key": key_code, "hwid": "hw-2"})

        assert response.status_code == 409


def test_activate_unknown_key_is_not_found(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        response = client.post(
            "/license/activate", json={"license_key": "TGPL-0000-0000-0000-0000", "hwid": "hw-1"}
        )
    assert response.status_code == 404


def test_revoked_key_cannot_activate(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        generated = client.post(
            "/admin/keys",
            json={"tier": "week", "count": 1},
            headers={"X-Admin-Key": _ADMIN_KEY},
        ).json()["keys"][0]
        client.post(
            f"/admin/keys/{generated['id']}/revoke",
            headers={"X-Admin-Key": _ADMIN_KEY},
        )

        response = client.post(
            "/license/activate", json={"license_key": generated["key_code"], "hwid": "hw-1"}
        )
        assert response.status_code == 403


def test_reset_device_allows_activation_on_a_new_device(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        generated = client.post(
            "/admin/keys",
            json={"tier": "week", "count": 1},
            headers={"X-Admin-Key": _ADMIN_KEY},
        ).json()["keys"][0]
        client.post("/license/activate", json={"license_key": generated["key_code"], "hwid": "hw-1"})

        client.post(
            f"/admin/keys/{generated['id']}/reset-device",
            headers={"X-Admin-Key": _ADMIN_KEY},
        )

        response = client.post(
            "/license/activate", json={"license_key": generated["key_code"], "hwid": "hw-2"}
        )
        assert response.status_code == 200


def test_list_keys_requires_admin_and_paginates(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        client.post(
            "/admin/keys",
            json={"tier": "week", "count": 5},
            headers={"X-Admin-Key": _ADMIN_KEY},
        )

        unauthorized = client.get("/admin/keys")
        assert unauthorized.status_code == 401

        page = client.get("/admin/keys?limit=2&offset=0", headers={"X-Admin-Key": _ADMIN_KEY})
        assert page.status_code == 200
        body = page.json()
        assert body["total"] == 5
        assert len(body["items"]) == 2


def test_revoke_unknown_key_is_not_found(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        response = client.post("/admin/keys/999/revoke", headers={"X-Admin-Key": _ADMIN_KEY})
    assert response.status_code == 404


def test_health_does_not_require_admin_key(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        response = client.get("/health")
    assert response.status_code == 200


def test_version_reports_configured_latest_version(monkeypatch, tmp_path):
    monkeypatch.setenv("LATEST_LAUNCHER_VERSION", "2.3.4")
    with _client(monkeypatch, tmp_path) as client:
        response = client.get("/version")
    assert response.status_code == 200
    assert response.json()["latest_version"] == "2.3.4"


def test_version_defaults_when_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("LATEST_LAUNCHER_VERSION", raising=False)
    with _client(monkeypatch, tmp_path) as client:
        response = client.get("/version")
    assert response.status_code == 200
    assert response.json()["latest_version"] == "0.0.0"
