"""tests/test_account_check_feature.py — tg_pool/features/account_check.py (MODE=check_accounts)."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import tg_pool.bootstrap as bootstrap
from tg_pool.accounts.health_checker import AccountStatus, HealthResult, PoolHealthReport
from tg_pool.config import AccountConfig
from tg_pool.features import account_check

pytestmark = pytest.mark.unit


def make_account(phone: str) -> AccountConfig:
    return AccountConfig(api_id=1, api_hash="h" * 32, phone=phone)


class _FakeHealthChecker:
    def __init__(self, result_by_phone):
        self._result_by_phone = result_by_phone
        self.calls = []

    async def check_pool_health(self, accounts, deep_check=False):
        self.calls.append(([a.phone for a in accounts], deep_check))
        return PoolHealthReport(results=[self._result_by_phone[a.phone] for a in accounts])


async def test_no_accounts_logs_error_and_returns(monkeypatch, caplog):
    caplog.set_level(logging.ERROR)
    monkeypatch.setattr(bootstrap, "load_accounts", lambda: ([], []))
    monkeypatch.setattr(bootstrap, "load_tdata_accounts", AsyncMock(return_value=[]))

    await account_check.run(None, logging.getLogger("test"))

    assert any("Аккаунты не найдены" in r.message for r in caplog.records)


async def test_checks_primary_spare_and_tdata_accounts(monkeypatch):
    primary = [make_account("+1")]
    spares = [make_account("+2")]
    tdata_accounts = [make_account("+3")]

    monkeypatch.setattr(bootstrap, "load_accounts", lambda: (primary, spares))
    monkeypatch.setattr(bootstrap, "load_tdata_accounts", AsyncMock(return_value=tdata_accounts))
    monkeypatch.setattr(bootstrap, "build_db_session_factory", lambda: None)
    monkeypatch.setattr(bootstrap, "build_account_repository", lambda *_: None)

    checker = _FakeHealthChecker({
        "+1": HealthResult(phone="+1", status=AccountStatus.ALIVE),
        "+2": HealthResult(phone="+2", status=AccountStatus.BANNED),
        "+3": HealthResult(phone="+3", status=AccountStatus.UNAUTHORIZED),
    })
    monkeypatch.setattr(bootstrap, "build_health_checker", lambda policy, event_bus=None: checker)

    with patch("tg_pool.monitoring.monitor.LiveMonitor.print_pool_table") as mock_print:
        await account_check.run(None, logging.getLogger("test"))

    assert set(checker.calls[0][0]) == {"+1", "+2", "+3"}
    mock_print.assert_called_once()
    printed_entries = mock_print.call_args[0][0]
    assert {e.account.phone for e in printed_entries} == {"+1", "+2", "+3"}
    assert {e.state.status for e in printed_entries} == {
        AccountStatus.ALIVE, AccountStatus.BANNED, AccountStatus.UNAUTHORIZED,
    }


async def test_deep_flag_read_from_env(monkeypatch):
    monkeypatch.setenv("ACCOUNT_CHECK_DEEP", "1")
    monkeypatch.setattr(bootstrap, "load_accounts", lambda: ([make_account("+1")], []))
    monkeypatch.setattr(bootstrap, "load_tdata_accounts", AsyncMock(return_value=[]))
    monkeypatch.setattr(bootstrap, "build_db_session_factory", lambda: None)
    monkeypatch.setattr(bootstrap, "build_account_repository", lambda *_: None)

    checker = _FakeHealthChecker({"+1": HealthResult(phone="+1", status=AccountStatus.ALIVE)})
    monkeypatch.setattr(bootstrap, "build_health_checker", lambda policy, event_bus=None: checker)

    with patch("tg_pool.monitoring.monitor.LiveMonitor.print_pool_table"):
        await account_check.run(None, logging.getLogger("test"))

    assert checker.calls == [(["+1"], True)]


async def test_results_persisted_via_registry_close(monkeypatch):
    monkeypatch.setattr(bootstrap, "load_accounts", lambda: ([make_account("+1")], []))
    monkeypatch.setattr(bootstrap, "load_tdata_accounts", AsyncMock(return_value=[]))
    monkeypatch.setattr(bootstrap, "build_db_session_factory", lambda: None)
    monkeypatch.setattr(bootstrap, "build_account_repository", lambda *_: None)

    checker = _FakeHealthChecker({"+1": HealthResult(phone="+1", status=AccountStatus.FROZEN)})
    monkeypatch.setattr(bootstrap, "build_health_checker", lambda policy, event_bus=None: checker)

    registries = []
    from tg_pool.accounts.account_registry import AccountRegistry
    real_init = AccountRegistry.__init__

    def _tracking_init(self, *a, **kw):
        real_init(self, *a, **kw)
        registries.append(self)

    with (
        patch.object(AccountRegistry, "__init__", _tracking_init),
        patch("tg_pool.monitoring.monitor.LiveMonitor.print_pool_table"),
    ):
        await account_check.run(None, logging.getLogger("test"))

    assert len(registries) == 1
    assert registries[0].get("+1").state.status == AccountStatus.FROZEN
