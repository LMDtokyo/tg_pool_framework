"""tests/test_bootstrap.py — Unit tests for src/bootstrap.py shared helpers."""

import builtins
import json
import logging
from unittest.mock import ANY, AsyncMock, patch

import pytest

import src.bootstrap as bootstrap
from src.config import AccountConfig

pytestmark = pytest.mark.unit


def test_env_int_reads_default_when_unset(monkeypatch):
    monkeypatch.delenv("SOME_INT_VAR", raising=False)
    assert bootstrap.env_int("SOME_INT_VAR", "5") == 5


def test_env_int_reads_set_value(monkeypatch):
    monkeypatch.setenv("SOME_INT_VAR", "42")
    assert bootstrap.env_int("SOME_INT_VAR", "5") == 42


def test_env_int_bad_value_names_the_variable(monkeypatch):
    """
    Regression: a typo like TG_API_ID_1=abc used to abort startup with a bare
    ValueError giving no hint which of ~20 env vars was the culprit.
    """
    monkeypatch.setenv("SOME_INT_VAR", "not-a-number")
    with pytest.raises(ValueError, match="SOME_INT_VAR"):
        bootstrap.env_int("SOME_INT_VAR", "5")


def test_env_float_reads_default_when_unset(monkeypatch):
    monkeypatch.delenv("SOME_FLOAT_VAR", raising=False)
    assert bootstrap.env_float("SOME_FLOAT_VAR", "2.5") == 2.5


def test_env_float_bad_value_names_the_variable(monkeypatch):
    monkeypatch.setenv("SOME_FLOAT_VAR", "not-a-number")
    with pytest.raises(ValueError, match="SOME_FLOAT_VAR"):
        bootstrap.env_float("SOME_FLOAT_VAR", "2.5")


def test_log_crypto_backend_reports_cryptg_when_available(caplog):
    caplog.set_level(logging.INFO)
    bootstrap.log_crypto_backend(logging.getLogger("test.crypto"))
    assert any("cryptg" in r.message and "активен" in r.message for r in caplog.records)


def test_log_crypto_backend_warns_when_cryptg_missing(monkeypatch, caplog):
    caplog.set_level(logging.WARNING)
    real_import = builtins.__import__

    def _blocked_import(name, *args, **kwargs):
        if name == "cryptg":
            raise ImportError("simulated: cryptg not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocked_import)
    bootstrap.log_crypto_backend(logging.getLogger("test.crypto"))
    assert any("не установлен" in r.message for r in caplog.records)


def _make_tdata_folder(root):
    tdata_dir = root / "acc1" / "tdata"
    tdata_dir.mkdir(parents=True)
    (tdata_dir / "key_datas").write_bytes(b"\x00")
    return tdata_dir


async def test_load_tdata_accounts_disabled_by_default(monkeypatch):
    monkeypatch.delenv("TDATA_ACCOUNTS_DIR", raising=False)
    assert await bootstrap.load_tdata_accounts() == []


async def test_load_tdata_accounts_missing_dir_returns_empty(monkeypatch, tmp_path):
    monkeypatch.setenv("TDATA_ACCOUNTS_DIR", str(tmp_path / "does_not_exist"))
    assert await bootstrap.load_tdata_accounts() == []


async def test_load_tdata_accounts_converts_found_folders(monkeypatch, tmp_path):
    tdata_root = tmp_path / "tdata_root"
    tdata_dir = _make_tdata_folder(tdata_root)
    monkeypatch.setenv("TDATA_ACCOUNTS_DIR", str(tdata_root))
    monkeypatch.delenv("TDATA_PASSWORDS_FILE", raising=False)

    fake_account = AccountConfig(api_id=1, api_hash="h", phone="+70010000000")
    mock_load = AsyncMock(return_value=fake_account)

    with patch("src.accounts.account_loader.load_from_tdata", new=mock_load):
        accounts = await bootstrap.load_tdata_accounts()

    assert accounts == [fake_account]
    mock_load.assert_awaited_once_with(str(tdata_dir.resolve()), session_dir=ANY, password=None)


async def test_load_tdata_accounts_reads_password_file(monkeypatch, tmp_path):
    tdata_root = tmp_path / "tdata_root"
    tdata_dir = _make_tdata_folder(tdata_root)
    resolved = str(tdata_dir.resolve())

    passwords_file = tmp_path / "passwords.json"
    passwords_file.write_text(json.dumps({resolved: "s3cr3t"}), encoding="utf-8")

    monkeypatch.setenv("TDATA_ACCOUNTS_DIR", str(tdata_root))
    monkeypatch.setenv("TDATA_PASSWORDS_FILE", str(passwords_file))

    fake_account = AccountConfig(api_id=1, api_hash="h", phone="+70010000000")
    mock_load = AsyncMock(return_value=fake_account)

    with patch("src.accounts.account_loader.load_from_tdata", new=mock_load):
        await bootstrap.load_tdata_accounts()

    mock_load.assert_awaited_once_with(resolved, session_dir=ANY, password="s3cr3t")


async def test_load_tdata_accounts_conversion_failure_is_skipped(monkeypatch, tmp_path):
    tdata_root = tmp_path / "tdata_root"
    _make_tdata_folder(tdata_root)
    monkeypatch.setenv("TDATA_ACCOUNTS_DIR", str(tdata_root))
    monkeypatch.delenv("TDATA_PASSWORDS_FILE", raising=False)

    mock_load = AsyncMock(side_effect=RuntimeError("boom"))

    with patch("src.accounts.account_loader.load_from_tdata", new=mock_load):
        accounts = await bootstrap.load_tdata_accounts()

    assert accounts == []


def test_load_proxies_from_env_stops_at_first_gap(monkeypatch):
    monkeypatch.setenv("PROXY_HOST_1", "proxy1.example.com")
    monkeypatch.setenv("PROXY_PORT_1", "1080")
    monkeypatch.delenv("PROXY_HOST_2", raising=False)
    monkeypatch.delenv("PROXY_PORT_2", raising=False)
    monkeypatch.setenv("PROXY_HOST_3", "proxy3.example.com")
    monkeypatch.setenv("PROXY_PORT_3", "1081")

    proxies = bootstrap.load_proxies_from_env()

    assert len(proxies) == 1
    assert proxies[0].host == "proxy1.example.com"
    assert proxies[0].port == 1080


def test_load_proxies_from_env_bad_port_names_the_variable(monkeypatch):
    monkeypatch.setenv("PROXY_HOST_1", "proxy1.example.com")
    monkeypatch.setenv("PROXY_PORT_1", "not-a-port")

    with pytest.raises(ValueError, match="PROXY_PORT_1"):
        bootstrap.load_proxies_from_env()


def test_load_proxies_from_env_empty_when_none_set(monkeypatch):
    monkeypatch.delenv("PROXY_HOST_1", raising=False)
    assert bootstrap.load_proxies_from_env() == []


def test_build_health_checker_reads_account_timeout(monkeypatch):
    from src.accounts.health_checker import HealthChecker
    from src.config import TimingPolicy

    monkeypatch.setenv("HEALTH_CONCURRENCY", "2")
    monkeypatch.setenv("HEALTH_ACCOUNT_TIMEOUT_SEC", "120")

    checker = bootstrap.build_health_checker(TimingPolicy(), event_bus=None)

    assert isinstance(checker, HealthChecker)
    assert checker._account_timeout_sec == 120
