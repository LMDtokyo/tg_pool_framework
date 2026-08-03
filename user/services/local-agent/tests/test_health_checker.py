"""
tests/test_health_checker.py — Tests for tg_pool/health_checker.py.

All Telethon network calls are mocked.

Scenarios:
  1. ALIVE — authorized, GetStateRequest succeeds, no SpamBot restriction.
  2. BANNED via UserDeactivatedBanError during GetStateRequest.
  3. BANNED via AuthKeyUnregisteredError during GetStateRequest.
  4. BANNED — is_user_authorized() returns False.
  5. PROXY_DEAD — connect() raises ConnectionError.
  6. FLOOD — FloodWaitError during GetStateRequest.
  7. SPAMBLOCK — @SpamBot replies with restriction text (deep_check=True).
  8. ALIVE + deep_check — @SpamBot replies with clean text.
  9. Parallel execution — check_pool_health on 3 accounts returns 3 results.
"""

from __future__ import annotations

import asyncio
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telethon.errors import (
    AuthKeyUnregisteredError,
    FloodWaitError,
    UserDeactivatedBanError,
)
from telethon.tl.functions.account import GetPasswordRequest

from tg_pool.config import AccountConfig, TimingPolicy
from tg_pool.accounts.health_checker import AccountStatus, HealthChecker


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FAST_POLICY = TimingPolicy(
    base_delay_sec=0.0,
    jitter_sec=0.0,
    inter_message_delay_sec=0.0,
    inter_message_jitter_sec=0.0,
    startup_jitter_max_sec=0.0,
    max_flood_retries=3,
)


def make_account(phone: str = "+79001234567") -> AccountConfig:
    return AccountConfig(api_id=1, api_hash="h" * 32, phone=phone)


def make_mock_client(
    *,
    connect_raises: Exception = None,
    authorized: bool = True,
    state_raises: Exception = None,
    spambot_messages=None,
    has_2fa: bool = False,
    password_raises: Exception = None,
) -> MagicMock:
    """
    Builds a mock TelegramClient for health checker tests.

    connect_raises    — if set, connect() raises this.
    authorized        — return value of is_user_authorized().
    state_raises      — if set, GetStateRequest call raises this.
    spambot_messages  — list of mock messages returned by get_messages(SpamBot).
    has_2fa           — GetPasswordRequest's has_password field.
    password_raises   — if set, GetPasswordRequest call raises this.

    client(...) dispatches by request type so GetPasswordRequest and
    GetStateRequest can be configured independently instead of sharing one
    blunt return_value/side_effect.
    """
    client = AsyncMock()

    if connect_raises:
        client.connect = AsyncMock(side_effect=connect_raises)
    else:
        client.connect = AsyncMock()

    client.is_user_authorized = AsyncMock(return_value=authorized)

    async def _dispatch_call(request):
        if isinstance(request, GetPasswordRequest):
            if password_raises:
                raise password_raises
            password_info = MagicMock()
            password_info.has_password = has_2fa
            return password_info
        if state_raises:
            raise state_raises
        return AsyncMock()

    client.side_effect = _dispatch_call

    client.disconnect = AsyncMock()
    client.is_connected = MagicMock(return_value=True)

    # SpamBot mocks
    client.get_entity = AsyncMock(return_value=MagicMock(id=178220800))
    client.send_message = AsyncMock()
    if spambot_messages is not None:
        client.get_messages = AsyncMock(return_value=spambot_messages)
    else:
        client.get_messages = AsyncMock(return_value=[])

    return client


def make_spambot_message(text: str, from_bot: bool = True) -> MagicMock:
    msg = MagicMock()
    msg.text = text
    msg.out = False   # message FROM SpamBot (not sent by us)
    return msg


async def _raise_sqlite_locked():
    raise sqlite3.OperationalError("database is locked")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHealthCheckerStatus:
    async def test_alive_all_checks_pass(self):
        client = make_mock_client(authorized=True)

        checker = HealthChecker(policy=FAST_POLICY)
        with patch("tg_pool.accounts.health_checker.ClientFactory.build", return_value=client):
            result = await checker._run_checks(make_account(), deep_check=False)

        assert result.status == AccountStatus.ALIVE

    async def test_banned_user_deactivated(self):
        exc = UserDeactivatedBanError(request=None)
        client = make_mock_client(authorized=True, state_raises=exc)

        checker = HealthChecker(policy=FAST_POLICY)
        with patch("tg_pool.accounts.health_checker.ClientFactory.build", return_value=client):
            result = await checker._run_checks(make_account(), deep_check=False)

        assert result.status == AccountStatus.BANNED
        assert "UserDeactivatedBanError" in result.detail

    async def test_banned_auth_key_unregistered(self):
        exc = AuthKeyUnregisteredError(request=None)
        client = make_mock_client(authorized=True, state_raises=exc)

        checker = HealthChecker(policy=FAST_POLICY)
        with patch("tg_pool.accounts.health_checker.ClientFactory.build", return_value=client):
            result = await checker._run_checks(make_account(), deep_check=False)

        assert result.status == AccountStatus.BANNED
        assert "Auth key" in result.detail

    async def test_banned_not_authorized(self):
        client = make_mock_client(authorized=False)

        checker = HealthChecker(policy=FAST_POLICY)
        with patch("tg_pool.accounts.health_checker.ClientFactory.build", return_value=client):
            result = await checker._run_checks(make_account(), deep_check=False)

        assert result.status == AccountStatus.UNAUTHORIZED
        assert "not authorized" in result.detail.lower()

    async def test_proxy_dead_on_connection_error(self):
        client = make_mock_client(connect_raises=OSError("Connection refused"))

        checker = HealthChecker(policy=FAST_POLICY)
        with patch("tg_pool.accounts.health_checker.ClientFactory.build", return_value=client):
            result = await checker._run_checks(make_account(), deep_check=False)

        assert result.status == AccountStatus.PROXY_DEAD
        assert "Connection failed" in result.detail

    async def test_database_locked_is_retried_before_success(self):
        client = make_mock_client(authorized=True)
        client.connect = AsyncMock(side_effect=[
            sqlite3.OperationalError("database is locked"),
            sqlite3.OperationalError("database is locked"),
            None,
        ])

        checker = HealthChecker(policy=FAST_POLICY)
        with patch("tg_pool.accounts.health_checker.ClientFactory.build", return_value=client):
            with patch("tg_pool.accounts.health_checker.asyncio.sleep", AsyncMock()):
                result = await checker._run_checks_with_retries(make_account(), deep_check=False)

        assert result.status == AccountStatus.ALIVE
        assert client.connect.await_count == 3

    async def test_database_locked_on_disconnect_does_not_hide_success(self):
        client = make_mock_client(authorized=True)
        client.disconnect = MagicMock(return_value=asyncio.create_task(
            _raise_sqlite_locked()
        ))

        checker = HealthChecker(policy=FAST_POLICY)
        with patch("tg_pool.accounts.health_checker.ClientFactory.build", return_value=client):
            result = await checker._run_checks(make_account(), deep_check=False)

        assert result.status == AccountStatus.ALIVE

    async def test_flood_on_get_state(self):
        exc = FloodWaitError(request=None)
        exc.seconds = 120
        client = make_mock_client(authorized=True, state_raises=exc)

        checker = HealthChecker(policy=FAST_POLICY)
        with patch("tg_pool.accounts.health_checker.ClientFactory.build", return_value=client):
            result = await checker._run_checks(make_account(), deep_check=False)

        assert result.status == AccountStatus.FLOOD
        assert result.flood_wait_seconds == 120


class TestTwoFactorAndGeoDetection:
    async def test_has_2fa_true_when_password_set(self):
        client = make_mock_client(authorized=True, has_2fa=True)

        checker = HealthChecker(policy=FAST_POLICY)
        with patch("tg_pool.accounts.health_checker.ClientFactory.build", return_value=client):
            result = await checker._run_checks(make_account(), deep_check=False)

        assert result.status == AccountStatus.ALIVE
        assert result.has_2fa is True

    async def test_has_2fa_false_when_no_password(self):
        client = make_mock_client(authorized=True, has_2fa=False)

        checker = HealthChecker(policy=FAST_POLICY)
        with patch("tg_pool.accounts.health_checker.ClientFactory.build", return_value=client):
            result = await checker._run_checks(make_account(), deep_check=False)

        assert result.has_2fa is False

    async def test_2fa_check_failure_does_not_break_health_check(self):
        """GetPasswordRequest failing must not take down the whole check (like get_me())."""
        client = make_mock_client(authorized=True, password_raises=RuntimeError("rpc error"))

        checker = HealthChecker(policy=FAST_POLICY)
        with patch("tg_pool.accounts.health_checker.ClientFactory.build", return_value=client):
            result = await checker._run_checks(make_account(), deep_check=False)

        assert result.status == AccountStatus.ALIVE
        assert result.has_2fa is False

    async def test_2fa_carried_into_banned_result(self):
        exc = UserDeactivatedBanError(request=None)
        client = make_mock_client(authorized=True, state_raises=exc, has_2fa=True)

        checker = HealthChecker(policy=FAST_POLICY)
        with patch("tg_pool.accounts.health_checker.ClientFactory.build", return_value=client):
            result = await checker._run_checks(make_account(), deep_check=False)

        assert result.status == AccountStatus.BANNED
        assert result.has_2fa is True

    async def test_country_derived_from_phone(self):
        client = make_mock_client(authorized=True)

        checker = HealthChecker(policy=FAST_POLICY)
        with patch("tg_pool.accounts.health_checker.ClientFactory.build", return_value=client):
            result = await checker._run_checks(make_account("+79001234567"), deep_check=False)

        assert result.country == "RU"

    async def test_country_present_even_on_proxy_dead(self):
        """country is phone-derived/offline -- known regardless of how far the check gets."""
        client = make_mock_client(connect_raises=OSError("Connection refused"))

        checker = HealthChecker(policy=FAST_POLICY)
        with patch("tg_pool.accounts.health_checker.ClientFactory.build", return_value=client):
            result = await checker._run_checks(make_account("+12025551234"), deep_check=False)

        assert result.status == AccountStatus.PROXY_DEAD
        assert result.country == "US"

    async def test_country_none_for_unparseable_phone(self):
        client = make_mock_client(authorized=True)

        checker = HealthChecker(policy=FAST_POLICY)
        with patch("tg_pool.accounts.health_checker.ClientFactory.build", return_value=client):
            result = await checker._run_checks(make_account("not-a-phone"), deep_check=False)

        assert result.country is None

    async def test_account_state_carries_2fa_and_country(self):
        client = make_mock_client(authorized=True, has_2fa=True)

        checker = HealthChecker(policy=FAST_POLICY)
        with patch("tg_pool.accounts.health_checker.ClientFactory.build", return_value=client):
            result = await checker._run_checks(make_account("+79001234567"), deep_check=False)

        state = result.account_state
        assert state.has_2fa is True
        assert state.country == "RU"


class TestSpamBotCheck:
    async def test_spamblock_detected_from_bot_reply(self):
        restriction_msg = make_spambot_message(
            "Ваш аккаунт был ограничен в результате жалоб."
        )
        client = make_mock_client(
            authorized=True,
            spambot_messages=[restriction_msg],
        )

        checker = HealthChecker(policy=FAST_POLICY)
        with patch("tg_pool.accounts.health_checker.ClientFactory.build", return_value=client):
            with patch("tg_pool.accounts.health_checker._SPAMBOT_REPLY_TIMEOUT", 0.1):
                result = await checker._run_checks(make_account(), deep_check=True)

        assert result.status == AccountStatus.SPAMBLOCK
        assert "@SpamBot" in result.detail

    async def test_alive_when_spambot_reports_clean(self):
        clean_msg = make_spambot_message(
            "Good news, no limits are currently imposed on your account!"
        )
        client = make_mock_client(
            authorized=True,
            spambot_messages=[clean_msg],
        )

        checker = HealthChecker(policy=FAST_POLICY)
        with patch("tg_pool.accounts.health_checker.ClientFactory.build", return_value=client):
            with patch("tg_pool.accounts.health_checker._SPAMBOT_REPLY_TIMEOUT", 0.1):
                result = await checker._run_checks(make_account(), deep_check=True)

        assert result.status == AccountStatus.ALIVE

    async def test_alive_when_spambot_does_not_reply(self):
        """
        If @SpamBot doesn't reply within timeout, we do NOT mark as spamblock
        (fail-safe: no reply ≠ confirmed restriction).
        """
        client = make_mock_client(
            authorized=True,
            spambot_messages=[],  # no messages
        )

        checker = HealthChecker(policy=FAST_POLICY)
        with patch("tg_pool.accounts.health_checker.ClientFactory.build", return_value=client):
            with patch("tg_pool.accounts.health_checker._SPAMBOT_REPLY_TIMEOUT", 0.05):
                result = await checker._run_checks(make_account(), deep_check=True)

        assert result.status == AccountStatus.ALIVE


class TestPoolHealthCheck:
    async def test_parallel_check_returns_result_per_account(self):
        accounts = [make_account(f"+7900000000{i}") for i in range(3)]

        def build_mock(acc):
            return make_mock_client(authorized=True)

        checker = HealthChecker(policy=FAST_POLICY, concurrency=3)
        with patch("tg_pool.accounts.health_checker.ClientFactory.build", side_effect=build_mock):
            report = await checker.check_pool_health(accounts, deep_check=False)

        assert len(report.results) == 3
        assert len(report.alive) == 3

    async def test_mixed_statuses_in_pool(self):
        accounts = [
            make_account("+79001111111"),  # alive
            make_account("+79002222222"),  # banned
        ]

        call_count = [0]

        def build_mock(acc):
            call_count[0] += 1
            if call_count[0] == 1:
                return make_mock_client(authorized=True)
            exc = UserDeactivatedBanError(request=None)
            return make_mock_client(authorized=True, state_raises=exc)

        checker = HealthChecker(policy=FAST_POLICY, concurrency=2)
        with patch("tg_pool.accounts.health_checker.ClientFactory.build", side_effect=build_mock):
            report = await checker.check_pool_health(accounts, deep_check=False)

        assert len(report.alive) == 1
        assert len(report.banned) == 1

    async def test_stuck_account_times_out_without_blocking_pool_result(self):
        accounts = [
            make_account("+79001111111"),
            make_account("+79002222222"),
        ]

        async def _never_returns():
            await asyncio.sleep(10)

        def build_mock(acc):
            if acc.phone == "+79002222222":
                client = make_mock_client(authorized=True)
                client.connect = AsyncMock(side_effect=_never_returns)
                return client
            return make_mock_client(authorized=True)

        seen = []
        checker = HealthChecker(policy=FAST_POLICY, concurrency=2, account_timeout_sec=0.01)
        with patch("tg_pool.accounts.health_checker.ClientFactory.build", side_effect=build_mock):
            report = await checker.check_pool_health(
                accounts,
                deep_check=False,
                on_result=lambda result: seen.append(result) or asyncio.sleep(0),
            )

        assert {result.phone for result in seen} == {account.phone for account in accounts}
        assert len(report.alive) == 1
        assert any(
            result.phone == "+79002222222" and result.status == AccountStatus.UNKNOWN
            for result in report.results
        )

    def test_pool_report_summary_string(self):
        from tg_pool.accounts.health_checker import HealthResult, PoolHealthReport

        report = PoolHealthReport(results=[
            HealthResult("+7001", AccountStatus.ALIVE),
            HealthResult("+7002", AccountStatus.BANNED),
            HealthResult("+7003", AccountStatus.SPAMBLOCK),
        ])
        summary = report.summary()
        assert "alive=1" in summary
        assert "banned=1" in summary
        assert "spamblock=1" in summary
