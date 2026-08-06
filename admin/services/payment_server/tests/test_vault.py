from __future__ import annotations

import pytest

from payment_server.vault import VaultError, load_datamoll_credentials


pytestmark = pytest.mark.unit


class _FakeApprole:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    def login(self, role_id: str, secret_id: str):
        self.calls.append((role_id, secret_id))
        if self.fail:
            raise RuntimeError("invalid role/secret id")


class _FakeKvV2:
    def __init__(self, payload: dict | None):
        self.payload = payload

    def read_secret_version(self, *, path, mount_point, raise_on_deleted_version):
        if self.payload is None:
            raise RuntimeError("no secret at that path")
        return {"data": {"data": self.payload}}


class _FakeAuth:
    def __init__(self, approle: _FakeApprole):
        self.approle = approle


class _FakeSecrets:
    def __init__(self, kv_v2: _FakeKvV2):
        class _Kv:
            def __init__(self, v2):
                self.v2 = v2

        self.kv = _Kv(kv_v2)


class _FakeClient:
    def __init__(self, url: str, *, approle: _FakeApprole, kv_v2: _FakeKvV2, authenticated: bool = True):
        self.url = url
        self.auth = _FakeAuth(approle)
        self.secrets = _FakeSecrets(kv_v2)
        self._authenticated = authenticated

    def is_authenticated(self) -> bool:
        return self._authenticated


@pytest.fixture(autouse=True)
def _clear_vault_env(monkeypatch):
    for name in ("VAULT_ADDR", "VAULT_ROLE_ID", "VAULT_SECRET_ID"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.asyncio
async def test_returns_none_when_vault_not_configured():
    assert await load_datamoll_credentials() is None


@pytest.mark.asyncio
async def test_raises_when_vault_addr_set_without_role_credentials(monkeypatch):
    monkeypatch.setenv("VAULT_ADDR", "http://127.0.0.1:8202")
    with pytest.raises(VaultError, match="VAULT_ROLE_ID"):
        await load_datamoll_credentials()


@pytest.mark.asyncio
async def test_reads_credentials_from_kv_via_approle(monkeypatch):
    monkeypatch.setenv("VAULT_ADDR", "http://127.0.0.1:8202")
    monkeypatch.setenv("VAULT_ROLE_ID", "role-1")
    monkeypatch.setenv("VAULT_SECRET_ID", "secret-1")

    approle = _FakeApprole()
    kv_v2 = _FakeKvV2({"provider_key": "hpk_test", "provider_secret": "hps_test"})
    fake_client = _FakeClient("http://127.0.0.1:8202", approle=approle, kv_v2=kv_v2)

    import payment_server.vault as vault_module

    monkeypatch.setattr(vault_module.hvac, "Client", lambda url: fake_client)

    result = await load_datamoll_credentials()

    assert result == ("hpk_test", "hps_test")
    assert approle.calls == [("role-1", "secret-1")]


@pytest.mark.asyncio
async def test_raises_on_approle_login_failure(monkeypatch):
    monkeypatch.setenv("VAULT_ADDR", "http://127.0.0.1:8202")
    monkeypatch.setenv("VAULT_ROLE_ID", "role-1")
    monkeypatch.setenv("VAULT_SECRET_ID", "wrong-secret")

    approle = _FakeApprole(fail=True)
    kv_v2 = _FakeKvV2(None)
    fake_client = _FakeClient("http://127.0.0.1:8202", approle=approle, kv_v2=kv_v2)

    import payment_server.vault as vault_module

    monkeypatch.setattr(vault_module.hvac, "Client", lambda url: fake_client)

    with pytest.raises(VaultError, match="AppRole login failed"):
        await load_datamoll_credentials()


@pytest.mark.asyncio
async def test_raises_when_secret_missing_expected_fields(monkeypatch):
    monkeypatch.setenv("VAULT_ADDR", "http://127.0.0.1:8202")
    monkeypatch.setenv("VAULT_ROLE_ID", "role-1")
    monkeypatch.setenv("VAULT_SECRET_ID", "secret-1")

    approle = _FakeApprole()
    kv_v2 = _FakeKvV2({"provider_key": "hpk_test"})  # missing provider_secret
    fake_client = _FakeClient("http://127.0.0.1:8202", approle=approle, kv_v2=kv_v2)

    import payment_server.vault as vault_module

    monkeypatch.setattr(vault_module.hvac, "Client", lambda url: fake_client)

    with pytest.raises(VaultError, match="missing provider_key/provider_secret"):
        await load_datamoll_credentials()
