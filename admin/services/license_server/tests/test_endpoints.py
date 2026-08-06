from datetime import datetime

from fastapi.testclient import TestClient
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from license_server.app import app
from license_server.signing import canonical_payload


def verify_activation(*, license_key, hwid, tier, expires_at, signature_hex, public_key_hex):
    """Contract-level verification without importing any customer-side source."""
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex)).verify(
            bytes.fromhex(signature_hex),
            canonical_payload(license_key, hwid, tier, expires_at),
        )
        return True
    except (InvalidSignature, ValueError):
        return False


def _normalize(iso_string: str) -> str:
    """Pydantic serializes UTC datetimes with a 'Z' suffix; the real client (see
    the customer client parses the response into a datetime and re-serializes
    it via datetime.isoformat() (always '+00:00', never 'Z') before verifying --
    that's the exact string the server signed. Tests must normalize the same way
    instead of comparing against the raw wire string."""
    return datetime.fromisoformat(iso_string).isoformat()

_ADMIN_KEY = "test-admin-key"
# Throwaway Ed25519 pair for tests only -- unrelated to the real key pair
# (private half lives only in the deployed license server's environment,
# public half is baked into the released customer client). Generated with
# license_server/generate_signing_key.py.
_SIGNING_PRIVATE_KEY = "536d31e2f677ece07053995d7bfe5cc73c5b36a3706f4f402ddd01d5a468bf7e"
_SIGNING_PUBLIC_KEY = "e2982c3a0dda4a4995e02b48089305c2d4a3227bc66ff85f7a39522834da49f7"


def _client(monkeypatch, tmp_path):
    db_path = (tmp_path / "license.db").as_posix()
    monkeypatch.setenv("LICENSE_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("LICENSE_ADMIN_API_KEY", _ADMIN_KEY)
    monkeypatch.setenv("LICENSE_SIGNING_PRIVATE_KEY", _SIGNING_PRIVATE_KEY)
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
        assert verify_activation(
            license_key=key_code,
            hwid="machine-a-hardware-uuid",
            tier=body["tier"],
            expires_at=_normalize(body["expires_at"]),
            signature_hex=body["signature"],
            public_key_hex=_SIGNING_PUBLIC_KEY,
        )


def test_activate_response_signature_rejects_a_tampered_field(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        generated = client.post(
            "/admin/keys",
            json={"tier": "month", "count": 1},
            headers={"X-Admin-Key": _ADMIN_KEY},
        )
        key_code = generated.json()["keys"][0]["key_code"]

        activated = client.post(
            "/license/activate",
            json={"license_key": key_code, "hwid": "machine-a-hardware-uuid"},
        )
        body = activated.json()

        # Simulates a response tampered in transit -- e.g. a bumped expiry.
        assert not verify_activation(
            license_key=key_code,
            hwid="machine-a-hardware-uuid",
            tier=body["tier"],
            expires_at="2099-01-01T00:00:00+00:00",
            signature_hex=body["signature"],
            public_key_hex=_SIGNING_PUBLIC_KEY,
        )


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
    monkeypatch.setenv("LATEST_LAUNCHER_DOWNLOAD_URL", "https://example.test/Setup-2.3.4.exe")
    with _client(monkeypatch, tmp_path) as client:
        response = client.get("/version")
    assert response.status_code == 200
    body = response.json()
    assert body["latest_version"] == "2.3.4"
    assert body["download_url"] == "https://example.test/Setup-2.3.4.exe"


def test_version_defaults_when_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("LATEST_LAUNCHER_VERSION", raising=False)
    monkeypatch.delenv("LATEST_LAUNCHER_DOWNLOAD_URL", raising=False)
    with _client(monkeypatch, tmp_path) as client:
        response = client.get("/version")
    assert response.status_code == 200
    body = response.json()
    assert body["latest_version"] == "0.0.0"
    assert body["download_url"] == ""


def test_profile_names_requires_no_auth_and_returns_nonempty_pools(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        response = client.get("/profile-names")
    assert response.status_code == 200
    body = response.json()
    assert len(body["first_names"]) > 0
    assert len(body["last_names"]) > 0
    assert all(isinstance(name, str) for name in body["first_names"])
