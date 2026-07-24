"""tests/test_cooldown_scheduler.py — CooldownScheduler sweep/loop behaviour."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from src.accounts.account_registry import AccountRegistry
from src.accounts.cooldown_scheduler import CooldownScheduler
from src.config import AccountConfig
from src.accounts.health_checker import AccountState, AccountStatus, HealthResult, PoolHealthReport

pytestmark = pytest.mark.unit


class _FakeHealthChecker:
    def __init__(self, result_by_phone):
        self._result_by_phone = result_by_phone
        self.calls: list = []

    async def check_pool_health(self, accounts, deep_check=False):
        self.calls.append([a.phone for a in accounts])
        results = [self._result_by_phone[a.phone] for a in accounts]
        return PoolHealthReport(results=results)


def _account(phone: str) -> AccountConfig:
    return AccountConfig(api_id=1, api_hash="h", phone=phone)


async def _registry_with(phone: str, status: AccountStatus, expires: datetime) -> AccountRegistry:
    registry = AccountRegistry()
    await registry.register(_account(phone))
    await registry.update_state(
        phone,
        AccountState(status=status, restriction_expires=expires),
    )
    return registry


async def test_sweep_ignores_accounts_not_yet_expired():
    future = datetime.now(timezone.utc) + timedelta(hours=5)
    registry = await _registry_with("+1", AccountStatus.SPAMBLOCK, future)
    checker = _FakeHealthChecker({})
    scheduler = CooldownScheduler(registry, checker, poll_interval=0.01)

    await scheduler._sweep_once()

    assert checker.calls == []
    assert registry.get("+1").state.status == AccountStatus.SPAMBLOCK


async def test_sweep_rechecks_expired_accounts_and_updates_registry():
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    registry = await _registry_with("+1", AccountStatus.SPAMBLOCK, past)
    checker = _FakeHealthChecker({
        "+1": HealthResult(phone="+1", status=AccountStatus.ALIVE, detail="clean again"),
    })
    scheduler = CooldownScheduler(registry, checker, poll_interval=0.01)

    await scheduler._sweep_once()

    assert checker.calls == [["+1"]]
    assert registry.get("+1").state.status == AccountStatus.ALIVE


async def test_sweep_ignores_alive_accounts():
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    registry = await _registry_with("+1", AccountStatus.ALIVE, past)
    checker = _FakeHealthChecker({})
    scheduler = CooldownScheduler(registry, checker, poll_interval=0.01)

    await scheduler._sweep_once()

    assert checker.calls == []


async def test_run_returns_immediately_if_shutdown_already_set():
    registry = AccountRegistry()
    checker = _FakeHealthChecker({})
    scheduler = CooldownScheduler(registry, checker, poll_interval=10.0)

    shutdown_event = asyncio.Event()
    shutdown_event.set()

    await asyncio.wait_for(scheduler.run(shutdown_event), timeout=1.0)

    assert checker.calls == []


async def test_run_sweeps_then_stops_on_shutdown():
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    registry = await _registry_with("+1", AccountStatus.FLOOD, past)
    checker = _FakeHealthChecker({
        "+1": HealthResult(phone="+1", status=AccountStatus.ALIVE, detail="ok"),
    })
    scheduler = CooldownScheduler(registry, checker, poll_interval=0.05)
    shutdown_event = asyncio.Event()

    async def _stop_soon():
        await asyncio.sleep(0.1)
        shutdown_event.set()

    stopper = asyncio.create_task(_stop_soon())
    await asyncio.wait_for(scheduler.run(shutdown_event), timeout=2.0)
    await stopper

    assert checker.calls == [["+1"]]
    assert registry.get("+1").state.status == AccountStatus.ALIVE
