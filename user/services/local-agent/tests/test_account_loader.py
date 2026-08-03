"""
tests/test_account_loader.py — Tests for tg_pool/account_loader.py.

Covers:
  1. ProxyAllocator Round-Robin with accounts_per_proxy=1 (default)
  2. ProxyAllocator Round-Robin with accounts_per_proxy=2
  3. ProxyAllocator with no proxies → all None
  4. ProxyAllocator cycling beyond proxy list length
  5. ProxyAllocator.assign() batch method
  6. load_from_session_json_pair — success path
  7. load_from_session_json_pair — missing JSON → FileNotFoundError
  8. load_from_session_json_pair — missing .session → FileNotFoundError
  9. load_from_session_json_pair — malformed JSON → ValueError
  10. load_accounts_from_directory — mixed session+json and bare session
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import List, Optional
from unittest.mock import AsyncMock, patch

import pytest

from tg_pool.accounts.account_loader import (
    ProxyAllocator,
    load_from_session_json_pair,
    load_from_tdata,
    load_accounts_from_directory,
)
from tg_pool.api.telegram_auth import FingerprintCatalog, TelegramFingerprint
from tg_pool.config import ProxyConfig
from tg_pool.proxy.tdata_converter import TDataConverter, TDataFingerprint, TDataSessionResult


def make_fingerprint(device: str, app_version: str) -> TelegramFingerprint:
    return TelegramFingerprint(
        app_id=1, app_hash="a" * 32, sdk=23, device=device, app_version=app_version,
        lang_code="en", system_lang_code="en", lang_pack="android", tz_offset=0, perf_cat=0,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_proxies(n: int) -> List[ProxyConfig]:
    return [ProxyConfig(host=f"proxy{i}.example.com", port=1080 + i) for i in range(n)]


# ---------------------------------------------------------------------------
# ProxyAllocator
# ---------------------------------------------------------------------------

class TestProxyAllocatorRoundRobin:
    def test_single_proxy_always_same(self):
        proxies = make_proxies(1)
        allocator = ProxyAllocator(proxies, accounts_per_proxy=1)
        results = allocator.assign(5)
        assert all(p == proxies[0] for p in results)

    def test_one_account_per_proxy(self):
        """
        accounts_per_proxy=1: each call advances to the next proxy.
        With 3 proxies and 6 accounts: P0, P1, P2, P0, P1, P2
        """
        proxies = make_proxies(3)
        allocator = ProxyAllocator(proxies, accounts_per_proxy=1)
        results = allocator.assign(6)
        assert results == [proxies[0], proxies[1], proxies[2],
                           proxies[0], proxies[1], proxies[2]]

    def test_two_accounts_per_proxy(self):
        """
        accounts_per_proxy=2 and 3 proxies for 7 accounts:
          A0→P0, A1→P0, A2→P1, A3→P1, A4→P2, A5→P2, A6→P0
        """
        proxies = make_proxies(3)
        allocator = ProxyAllocator(proxies, accounts_per_proxy=2)
        results = allocator.assign(7)
        expected = [
            proxies[0], proxies[0],
            proxies[1], proxies[1],
            proxies[2], proxies[2],
            proxies[0],  # wraps around
        ]
        assert results == expected

    def test_more_accounts_than_proxies_cycles(self):
        """2 proxies for 5 accounts → P0, P1, P0, P1, P0"""
        proxies = make_proxies(2)
        allocator = ProxyAllocator(proxies, accounts_per_proxy=1)
        results = allocator.assign(5)
        assert results[0] == proxies[0]
        assert results[1] == proxies[1]
        assert results[2] == proxies[0]
        assert results[3] == proxies[1]
        assert results[4] == proxies[0]

    def test_no_proxies_returns_all_none(self):
        allocator = ProxyAllocator([], accounts_per_proxy=1)
        results = allocator.assign(5)
        assert results == [None] * 5

    def test_next_is_consistent_with_assign(self):
        """Manual next() calls should match assign()."""
        proxies = make_proxies(2)
        a1 = ProxyAllocator(proxies, accounts_per_proxy=2)
        a2 = ProxyAllocator(proxies, accounts_per_proxy=2)

        manual = [a1.next() for _ in range(6)]
        batch = a2.assign(6)
        assert manual == batch

    def test_invalid_ratio_raises(self):
        with pytest.raises(ValueError):
            ProxyAllocator(make_proxies(1), accounts_per_proxy=0)


# ---------------------------------------------------------------------------
# load_from_session_json_pair
# ---------------------------------------------------------------------------

class TestLoadFromSessionJsonPair:
    def _write_pair(self, tmp: Path, data: dict, write_session: bool = True) -> Path:
        """Writes a .session + .json pair to tmp dir and returns session path."""
        session_file = tmp / "79001234567.session"
        json_file = tmp / "79001234567.json"
        if write_session:
            session_file.write_bytes(b"fake session data")
        json_file.write_text(json.dumps(data), encoding="utf-8")
        return session_file

    def test_loads_all_required_fields(self, tmp_path):
        data = {
            "app_id": 12345678,
            "app_hash": "abc" * 11,
            "phone": "+79001234567",
        }
        sf = self._write_pair(tmp_path, data)
        account = load_from_session_json_pair(str(sf))

        assert account.api_id == 12345678
        assert account.api_hash == "abc" * 11
        assert account.phone == "+79001234567"

    def test_api_id_and_api_hash_are_accepted_as_aliases(self, tmp_path):
        data = {
            "api_id": 12345678,
            "api_hash": "abc" * 11,
            "phone": "+79001234567",
        }
        sf = self._write_pair(tmp_path, data)
        account = load_from_session_json_pair(str(sf))

        assert account.api_id == 12345678
        assert account.api_hash == "abc" * 11

    def test_app_id_wins_when_both_app_id_and_api_id_are_present(self, tmp_path):
        data = {
            "app_id": 111,
            "api_id": 222,
            "app_hash": "abc" * 11,
            "phone": "+79001234567",
        }
        sf = self._write_pair(tmp_path, data)
        account = load_from_session_json_pair(str(sf))

        assert account.api_id == 111

    def test_missing_both_app_id_and_api_id_raises(self, tmp_path):
        data = {"app_hash": "abc" * 11, "phone": "+79001234567"}
        sf = self._write_pair(tmp_path, data)

        with pytest.raises(ValueError, match="app_id/api_id"):
            load_from_session_json_pair(str(sf))

    def test_json_phone_without_plus_is_canonicalized(self, tmp_path):
        data = {
            "app_id": 12345678,
            "app_hash": "abc" * 11,
            "phone": "79001234567",
        }
        sf = self._write_pair(tmp_path, data)

        account = load_from_session_json_pair(str(sf))

        assert account.phone == "+79001234567"

    def test_loads_optional_fingerprint_fields(self, tmp_path):
        data = {
            "app_id": 1,
            "app_hash": "h",
            "phone": "+7",
            "device": "Pixel 7",
            "system": "Android 13",
            "app_version": "9.9.9",
        }
        sf = self._write_pair(tmp_path, data)
        account = load_from_session_json_pair(str(sf))

        assert account.device_model == "Pixel 7"
        assert account.system_version == "Android 13"
        assert account.app_version == "9.9.9"

    def test_non_numeric_desktop_sdk_does_not_block_loading(self, tmp_path):
        data = {
            "app_id": 2040,
            "app_hash": "h",
            "phone": "13438921715",
            "device": "Asterope",
            "system": "Windows 11",
            "app_version": "6.9.4 x64",
            "sdk": "Windows 11 x64",
        }
        sf = self._write_pair(tmp_path, data)

        account = load_from_session_json_pair(str(sf))

        assert account.phone == "+13438921715"
        assert account.device_model == "Asterope"
        assert account.system_version == "Windows 11"
        assert account.sdk == 0

    def test_default_fingerprint_when_missing(self, tmp_path):
        data = {"app_id": 1, "app_hash": "h", "phone": "+7"}
        sf = self._write_pair(tmp_path, data)
        account = load_from_session_json_pair(str(sf))

        assert account.device_model == "Samsung Galaxy S23"
        assert account.system_version == "Android 14"

    def test_proxy_is_assigned(self, tmp_path):
        data = {"app_id": 1, "app_hash": "h", "phone": "+7"}
        sf = self._write_pair(tmp_path, data)
        proxy = ProxyConfig(host="10.0.0.1", port=1080)
        account = load_from_session_json_pair(str(sf), proxy=proxy)

        assert account.proxy == proxy

    def test_missing_json_raises(self, tmp_path):
        session_file = tmp_path / "orphan.session"
        session_file.write_bytes(b"x")

        with pytest.raises(FileNotFoundError, match="JSON companion"):
            load_from_session_json_pair(str(session_file))

    def test_missing_session_raises(self, tmp_path):
        json_file = tmp_path / "noses.json"
        json_file.write_text(
            json.dumps({"app_id": 1, "app_hash": "h", "phone": "+7"}),
            encoding="utf-8",
        )
        with pytest.raises(FileNotFoundError, match="Session file"):
            load_from_session_json_pair(str(tmp_path / "noses.session"))

    def test_json_missing_required_field_raises(self, tmp_path):
        data = {"app_id": 1, "app_hash": "h"}  # phone missing
        sf = self._write_pair(tmp_path, data)

        with pytest.raises(ValueError, match="phone"):
            load_from_session_json_pair(str(sf))


# ---------------------------------------------------------------------------
# load_accounts_from_directory
# ---------------------------------------------------------------------------

class TestLoadAccountsFromDirectory:
    def test_loads_session_json_pairs(self, tmp_path):
        for phone in ["79001111111", "79002222222"]:
            (tmp_path / f"{phone}.session").write_bytes(b"x")
            (tmp_path / f"{phone}.json").write_text(
                json.dumps({"app_id": 1, "app_hash": "h", "phone": f"+{phone}"}),
                encoding="utf-8",
            )

        accounts = load_accounts_from_directory(str(tmp_path))
        assert len(accounts) == 2
        phones = {a.phone for a in accounts}
        assert "+79001111111" in phones

    def test_skips_bare_session_without_api_credentials(self, tmp_path):
        (tmp_path / "79001111111.session").write_bytes(b"x")
        # No .json companion, no api_id/api_hash passed
        accounts = load_accounts_from_directory(str(tmp_path))
        assert len(accounts) == 0

    def test_loads_bare_session_with_api_credentials(self, tmp_path):
        (tmp_path / "79001111111.session").write_bytes(b"x")
        accounts = load_accounts_from_directory(
            str(tmp_path), api_id=12345, api_hash="abc" * 11
        )
        assert len(accounts) == 1
        assert accounts[0].phone == "+79001111111"

    def test_proxy_distribution_two_per_proxy(self, tmp_path):
        """
        3 accounts, 2 proxies, accounts_per_proxy=2:
          A0→P0, A1→P0, A2→P1
        """
        for i in range(3):
            (tmp_path / f"7900000000{i}.session").write_bytes(b"x")
            (tmp_path / f"7900000000{i}.json").write_text(
                json.dumps({"app_id": 1, "app_hash": "h", "phone": f"+7900000000{i}"}),
                encoding="utf-8",
            )

        proxies = make_proxies(2)
        accounts = load_accounts_from_directory(
            str(tmp_path), proxies=proxies, accounts_per_proxy=2
        )

        assert len(accounts) == 3
        assert accounts[0].proxy == proxies[0]
        assert accounts[1].proxy == proxies[0]
        assert accounts[2].proxy == proxies[1]

    def test_not_a_directory_raises(self, tmp_path):
        fake_file = tmp_path / "not_a_dir"
        fake_file.write_bytes(b"")
        with pytest.raises(NotADirectoryError):
            load_accounts_from_directory(str(fake_file))

    def test_bare_sessions_with_a_catalog_get_distinct_fingerprints_and_sidecars(self, tmp_path):
        (tmp_path / "79001111111.session").write_bytes(b"x")
        (tmp_path / "79002222222.session").write_bytes(b"x")
        catalog = FingerprintCatalog(
            [make_fingerprint("Pixel 8", "10.1.0"), make_fingerprint("Galaxy S24", "10.2.0")]
        )

        accounts = load_accounts_from_directory(
            str(tmp_path), api_id=12345, api_hash="abc" * 11, fingerprint_catalog=catalog
        )

        assert len(accounts) == 2
        signatures = {(a.device_model, a.app_version) for a in accounts}
        assert signatures == {("Pixel 8", "10.1.0"), ("Galaxy S24", "10.2.0")}
        assert (tmp_path / "79001111111.json").exists()
        assert (tmp_path / "79002222222.json").exists()

    def test_bare_session_without_a_catalog_falls_back_to_defaults(self, tmp_path):
        (tmp_path / "79001111111.session").write_bytes(b"x")

        accounts = load_accounts_from_directory(
            str(tmp_path), api_id=12345, api_hash="abc" * 11
        )

        assert accounts[0].device_model == "Samsung Galaxy S23"
        assert not (tmp_path / "79001111111.json").exists()

    def test_used_fingerprints_set_is_shared_across_two_directories(self, tmp_path):
        primary_dir = tmp_path / "primary"
        spare_dir = tmp_path / "spare"
        primary_dir.mkdir()
        spare_dir.mkdir()
        (primary_dir / "79001111111.session").write_bytes(b"x")
        (spare_dir / "79002222222.session").write_bytes(b"x")
        catalog = FingerprintCatalog(
            [make_fingerprint("Pixel 8", "10.1.0"), make_fingerprint("Galaxy S24", "10.2.0")]
        )
        used: set = set()

        primary = load_accounts_from_directory(
            str(primary_dir), api_id=1, api_hash="a" * 32,
            fingerprint_catalog=catalog, used_fingerprints=used,
        )
        spare = load_accounts_from_directory(
            str(spare_dir), api_id=1, api_hash="a" * 32,
            fingerprint_catalog=catalog, used_fingerprints=used,
        )

        combined = {(a.device_model, a.app_version) for a in primary + spare}
        assert len(combined) == 2  # no duplicate assigned across the two directories


# ---------------------------------------------------------------------------
# load_from_tdata — delegates to TDataConverter (tg_pool/proxy/tdata_converter.py)
# ---------------------------------------------------------------------------

def _fake_session_result(tmp_path, phone="+79001234567") -> TDataSessionResult:
    return TDataSessionResult(
        session_path=tmp_path / "sessions" / "acc",
        fingerprint=TDataFingerprint(
            api_id=2040, api_hash="b18441a1ff607e10a989891a5462e627",
            device_model="Desktop", system_version="Windows 10", app_version="3.4.3 x64",
        ),
        phone=phone,
    )


class TestLoadFromTdata:
    async def test_builds_account_config_from_conversion_result(self, tmp_path):
        fake_result = _fake_session_result(tmp_path)
        tdata_dir = tmp_path / "tdata"

        with patch.object(
            TDataConverter, "tdata_to_session", new=AsyncMock(return_value=fake_result)
        ) as mock_convert:
            account = await load_from_tdata(str(tdata_dir), session_dir=str(tmp_path / "sessions"))

        mock_convert.assert_awaited_once_with(
            str(tdata_dir), str(tmp_path / "sessions"), None
        )
        assert account.api_id == 2040
        assert account.api_hash == "b18441a1ff607e10a989891a5462e627"
        assert account.device_model == "Desktop"
        assert account.system_version == "Windows 10"
        assert account.app_version == "3.4.3 x64"
        assert account.phone == "+79001234567"

    async def test_password_forwarded_to_converter(self, tmp_path):
        fake_result = _fake_session_result(tmp_path)
        with patch.object(
            TDataConverter, "tdata_to_session", new=AsyncMock(return_value=fake_result)
        ) as mock_convert:
            await load_from_tdata(str(tmp_path / "tdata"), password="s3cr3t")

        mock_convert.assert_awaited_once_with(str(tmp_path / "tdata"), "sessions", "s3cr3t")

    async def test_proxy_passed_through(self, tmp_path):
        fake_result = _fake_session_result(tmp_path)
        proxy = ProxyConfig(host="1.2.3.4", port=1080)

        with patch.object(TDataConverter, "tdata_to_session", new=AsyncMock(return_value=fake_result)):
            account = await load_from_tdata(str(tmp_path / "tdata"), proxy=proxy)

        assert account.proxy is proxy

    async def test_missing_phone_falls_back_to_tdata_dirname(self, tmp_path):
        fake_result = _fake_session_result(tmp_path, phone="")
        tdata_dir = tmp_path / "some_account_folder"

        with patch.object(TDataConverter, "tdata_to_session", new=AsyncMock(return_value=fake_result)):
            account = await load_from_tdata(str(tdata_dir))

        assert account.phone == "some_account_folder"

    async def test_raises_import_error_when_opentele_unavailable(self, tmp_path, monkeypatch):
        import tg_pool.accounts.account_loader as al
        monkeypatch.setattr(al, "_OPENTELE_OK", False)

        with pytest.raises(ImportError, match="opentele"):
            await load_from_tdata(str(tmp_path / "tdata"))

    async def test_conversion_error_propagates(self, tmp_path):
        from tg_pool.proxy.tdata_converter import TDataInvalidError

        with patch.object(
            TDataConverter, "tdata_to_session",
            new=AsyncMock(side_effect=TDataInvalidError("bad tdata")),
        ):
            with pytest.raises(TDataInvalidError):
                await load_from_tdata(str(tmp_path / "tdata"))
