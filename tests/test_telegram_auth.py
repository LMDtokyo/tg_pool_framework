from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from openpyxl import Workbook

from src.api.hero_sms_activation import HeroSmsActivationManager
from src.api.telegram_auth import FingerprintCatalog, TelegramAuthenticator
from src.config import ProxyConfig


pytestmark = pytest.mark.unit


def _write_fingerprints(path: Path) -> None:
    path.write_text(
        "APP_ID,APP_HASH,SDK,DEVICE,APP_VERSION,LANG_CODE,"
        "SYSTEM_LANG_CODE,LANG_PACK,TZ_OFFSET,PERF_CAT\n"
        "4,0123456789abcdef0123456789abcdef,31,Huawei Y6p,"
        "11.3.2 (53932),fr,fr-fr,android,0,2\n",
        encoding="utf-8",
    )


def test_fingerprint_catalog_loads_complete_row(tmp_path):
    source = tmp_path / "fingerprints.csv"
    _write_fingerprints(source)

    fingerprint = FingerprintCatalog.load(source).choose()

    assert fingerprint.app_id == 4
    assert fingerprint.sdk == 31
    assert fingerprint.device == "Huawei Y6p"
    assert fingerprint.lang_code == "fr"
    assert fingerprint.perf_cat == 2


def _write_two_fingerprints(path: Path) -> None:
    path.write_text(
        "APP_ID,APP_HASH,SDK,DEVICE,APP_VERSION,LANG_CODE,"
        "SYSTEM_LANG_CODE,LANG_PACK,TZ_OFFSET,PERF_CAT\n"
        "4,0123456789abcdef0123456789abcdef,31,Huawei Y6p,"
        "11.3.2 (53932),fr,fr-fr,android,0,2\n"
        "4,0123456789abcdef0123456789abcdef,33,Realme 11 Pro+,"
        "11.3.2 (53932),de,de-de,android,0,3\n",
        encoding="utf-8",
    )


def test_choose_avoids_signatures_already_in_use(tmp_path):
    source = tmp_path / "fingerprints.csv"
    _write_two_fingerprints(source)
    catalog = FingerprintCatalog.load(source)

    fingerprint = catalog.choose(avoid={("Huawei Y6p", "11.3.2 (53932)")})

    assert fingerprint.device == "Realme 11 Pro+"


def test_choose_falls_back_to_a_repeat_once_every_signature_is_taken(tmp_path):
    source = tmp_path / "fingerprints.csv"
    _write_two_fingerprints(source)
    catalog = FingerprintCatalog.load(source)
    all_signatures = {
        ("Huawei Y6p", "11.3.2 (53932)"),
        ("Realme 11 Pro+", "11.3.2 (53932)"),
    }

    fingerprint = catalog.choose(avoid=all_signatures)

    assert fingerprint.signature() in all_signatures


def test_fingerprint_catalog_loads_xlsx_workbook(tmp_path):
    source = tmp_path / "telegram_devices.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(
        [
            "APP_ID",
            "APP_HASH",
            "SDK",
            "DEVICE",
            "APP_VERSION",
            "LANG_CODE",
            "SYSTEM_LANG_CODE",
            "LANG_PACK",
            "TZ_OFFSET",
            "PERF_CAT",
        ]
    )
    worksheet.append(
        [
            4,
            "0123456789abcdef0123456789abcdef",
            33,
            "Realme 11 Pro+",
            "11.3.2 (53932)",
            "de",
            "de-de",
            "android",
            0,
            3,
        ]
    )
    workbook.save(source)
    workbook.close()

    fingerprint = FingerprintCatalog.load(source).choose()

    assert fingerprint.device == "Realme 11 Pro+"
    assert fingerprint.sdk == 33
    assert fingerprint.system_lang_code == "de-de"


@pytest.mark.asyncio
async def test_authenticator_saves_reusable_session_and_metadata(
    tmp_path, monkeypatch
):
    source = tmp_path / "fingerprints.csv"
    accounts_dir = tmp_path / "accounts"
    _write_fingerprints(source)

    class FakeClient:
        def __init__(self, account):
            self.account = account
            self.connected = False

        async def connect(self):
            self.connected = True

        def is_connected(self):
            return self.connected

        async def disconnect(self):
            Path(f"{self.account.session_path}.session").write_bytes(b"sqlite")
            self.connected = False

        async def send_code_request(self, phone):
            return SimpleNamespace(phone_code_hash="hash")

        async def sign_in(self, **kwargs):
            return SimpleNamespace(id=1)

        async def is_user_authorized(self):
            return True

    monkeypatch.setattr(
        "src.api.telegram_auth.ClientFactory.build",
        lambda account: FakeClient(account),
    )
    authenticator = TelegramAuthenticator(
        fingerprint_file=str(source),
        accounts_dir=str(accounts_dir),
    )

    login = await authenticator.begin("15550001111")
    assert await authenticator.submit_code(login, "54321") is True
    saved = await authenticator.save(login)

    session_file = accounts_dir / "15550001111.session"
    metadata_file = accounts_dir / "15550001111.json"
    assert saved.session_file == str(session_file)
    assert session_file.read_bytes() == b"sqlite"
    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    assert metadata["phone"] == "+15550001111"
    assert metadata["sdk"] == 31
    assert metadata["lang_pack"] == "android"


@pytest.mark.asyncio
async def test_authenticator_uses_registration_proxy_provider(tmp_path, monkeypatch):
    source = tmp_path / "fingerprints.csv"
    accounts_dir = tmp_path / "accounts"
    _write_fingerprints(source)
    proxy = ProxyConfig(
        host="10.10.10.10",
        port=1080,
        username="user",
        password="pass",
        proxy_type="socks5",
    )
    built_accounts = []

    class FakeClient:
        def __init__(self, account):
            self.account = account
            self.connected = False

        async def connect(self):
            self.connected = True

        def is_connected(self):
            return self.connected

        async def disconnect(self):
            self.connected = False

        async def send_code_request(self, phone):
            return SimpleNamespace(phone_code_hash="hash")

    async def proxy_provider():
        return proxy

    def build_client(account):
        built_accounts.append(account)
        return FakeClient(account)

    monkeypatch.setattr("src.api.telegram_auth.ClientFactory.build", build_client)
    authenticator = TelegramAuthenticator(
        fingerprint_file=str(source),
        accounts_dir=str(accounts_dir),
        proxy_provider=proxy_provider,
    )

    login = await authenticator.begin("15550001111")

    assert built_accounts[0].proxy is proxy
    assert login.account.proxy is proxy
    await authenticator.discard(login)


@pytest.mark.asyncio
async def test_authenticator_avoids_fingerprint_signatures_already_in_use(tmp_path, monkeypatch):
    source = tmp_path / "fingerprints.csv"
    accounts_dir = tmp_path / "accounts"
    _write_two_fingerprints(source)

    class FakeClient:
        def __init__(self, account):
            self.account = account
            self.connected = False

        async def connect(self):
            self.connected = True

        def is_connected(self):
            return self.connected

        async def disconnect(self):
            self.connected = False

        async def send_code_request(self, phone):
            return SimpleNamespace(phone_code_hash="hash")

    monkeypatch.setattr(
        "src.api.telegram_auth.ClientFactory.build", lambda account: FakeClient(account)
    )
    authenticator = TelegramAuthenticator(
        fingerprint_file=str(source),
        accounts_dir=str(accounts_dir),
        fingerprint_signatures_provider=lambda: [("Huawei Y6p", "11.3.2 (53932)")],
    )

    login = await authenticator.begin("15550001111")

    assert login.fingerprint.device == "Realme 11 Pro+"
    await authenticator.discard(login)


@pytest.mark.asyncio
async def test_authenticator_uses_the_profile_name_provider_when_given(tmp_path, monkeypatch):
    source = tmp_path / "fingerprints.csv"
    accounts_dir = tmp_path / "accounts"
    _write_two_fingerprints(source)

    class FakeClient:
        def __init__(self, account):
            self.account = account
            self.connected = False

        async def connect(self):
            self.connected = True

        def is_connected(self):
            return self.connected

        async def disconnect(self):
            self.connected = False

        async def send_code_request(self, phone):
            return SimpleNamespace(phone_code_hash="hash")

    monkeypatch.setattr(
        "src.api.telegram_auth.ClientFactory.build", lambda account: FakeClient(account)
    )
    authenticator = TelegramAuthenticator(
        fingerprint_file=str(source),
        accounts_dir=str(accounts_dir),
        profile_name_provider=lambda: ("Serverside", "Pooled"),
    )

    login = await authenticator.begin("15550001111")

    assert (login.first_name, login.last_name) == ("Serverside", "Pooled")
    await authenticator.discard(login)


@pytest.mark.asyncio
async def test_activation_manager_waits_for_launcher_two_factor(monkeypatch):
    request = AsyncMock(
        return_value={
            "activation_id": "123",
            "phone_number": "15550001111",
            "activation_cost": Decimal("0.15"),
            "currency": 840,
            "operator": "tele2",
            "can_get_another_sms": True,
        }
    )
    monkeypatch.setattr("src.api.hero_sms_activation.request_number_v2", request)
    monkeypatch.setattr(
        "src.api.hero_sms_activation.get_activation_status",
        AsyncMock(return_value=("STATUS_OK", "54321")),
    )
    monkeypatch.setattr(
        "src.api.hero_sms_activation.close_activation", AsyncMock()
    )

    class FakeAuthenticator:
        def __init__(self):
            self.password = None

        def validate_ready(self):
            pass

        async def begin(self, phone):
            return SimpleNamespace(phone="+15550001111")

        async def submit_code(self, login, code):
            return False

        async def submit_password(self, login, password):
            self.password = password

        async def save(self, login):
            return SimpleNamespace(
                account=SimpleNamespace(phone="+15550001111"),
                session_file="accounts/15550001111.session",
                created_new_account=False,
            )

        async def discard(self, login):
            pass

    authenticator = FakeAuthenticator()
    manager = HeroSmsActivationManager(
        authenticator=authenticator,
        two_factor_timeout_sec=5,
    )
    manager.start(
        api_key="secret-key",
        country_id=6,
        operator="any",
        target_count=1,
        concurrency=1,
        timeout_sec=30,
        max_price=Decimal("0.15"),
    )

    for _ in range(100):
        rows = manager.status()["rows"]
        if rows and rows[0]["needs_2fa"]:
            break
        await asyncio.sleep(0)

    row = manager.status()["rows"][0]
    assert row["stage"] == "waiting_2fa"
    manager.submit_two_factor(row["row_id"], "cloud-password")
    for _ in range(100):
        if manager.status()["rows"][0]["stage"] == "session_saved":
            break
        await asyncio.sleep(0)
    await manager.stop()

    row = manager.status()["rows"][0]
    assert authenticator.password == "cloud-password"
    assert row["stage"] == "session_saved"
    assert row["session_file"].endswith(".session")
