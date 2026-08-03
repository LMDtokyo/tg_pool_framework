"""tests/test_periodic_health_scheduler.py — PeriodicHealthScheduler sweep/loop behaviour."""

import asyncio

import pytest

from tg_pool.accounts.account_registry import AccountRegistry
from tg_pool.accounts.periodic_health_scheduler import PeriodicHealthScheduler
from tg_pool.config import AccountConfig
from tg_pool.accounts.health_checker import AccountState, AccountStatus, HealthResult, PoolHealthReport

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


async def test_sweep_rechecks_every_account_regardless_of_status():
    """Unlike CooldownScheduler, ALIVE accounts are rechecked too."""
    registry = AccountRegistry()
    await registry.register(_account("+1"))
    await registry.update_state("+1", AccountState(status=AccountStatus.ALIVE))

    checker = _FakeHealthChecker({
        "+1": HealthResult(phone="+1", status=AccountStatus.BANNED, detail="fresh ban"),
    })
    scheduler = PeriodicHealthScheduler([_account("+1")], registry, checker, poll_interval=60.0)

    await scheduler._sweep_once()

    assert checker.calls == [["+1"]]
    assert registry.get("+1").state.status == AccountStatus.BANNED


async def test_sweep_with_no_accounts_is_a_noop():
    registry = AccountRegistry()
    checker = _FakeHealthChecker({})
    scheduler = PeriodicHealthScheduler([], registry, checker, poll_interval=60.0)

    await scheduler._sweep_once()

    assert checker.calls == []


async def test_run_waits_before_first_sweep():
    """Sweep happens AFTER poll_interval, not immediately (unlike CooldownScheduler)."""
    registry = AccountRegistry()
    await registry.register(_account("+1"))
    checker = _FakeHealthChecker({
        "+1": HealthResult(phone="+1", status=AccountStatus.ALIVE),
    })
    scheduler = PeriodicHealthScheduler([_account("+1")], registry, checker, poll_interval=0.2)
    shutdown_event = asyncio.Event()

    async def _stop_after_first_sweep():
        await asyncio.sleep(0.05)
        assert checker.calls == []  # not yet -- still waiting out poll_interval
        await asyncio.sleep(0.3)
        shutdown_event.set()

    stopper = asyncio.create_task(_stop_after_first_sweep())
    await asyncio.wait_for(scheduler.run(shutdown_event), timeout=2.0)
    await stopper

    assert checker.calls == [["+1"]]


async def test_run_returns_immediately_if_shutdown_already_set():
    registry = AccountRegistry()
    checker = _FakeHealthChecker({})
    scheduler = PeriodicHealthScheduler([], registry, checker, poll_interval=10.0)
    shutdown_event = asyncio.Event()
    shutdown_event.set()

    await asyncio.wait_for(scheduler.run(shutdown_event), timeout=1.0)

    assert checker.calls == []


async def test_sweep_failure_does_not_crash_the_loop():
    registry = AccountRegistry()
    await registry.register(_account("+1"))

    class _BrokenChecker:
        async def check_pool_health(self, accounts, deep_check=False):
            raise RuntimeError("network blip")

    scheduler = PeriodicHealthScheduler(
        [_account("+1")], registry, _BrokenChecker(), poll_interval=0.05
    )
    shutdown_event = asyncio.Event()

    async def _stop_soon():
        await asyncio.sleep(0.15)
        shutdown_event.set()

    stopper = asyncio.create_task(_stop_soon())
    await asyncio.wait_for(scheduler.run(shutdown_event), timeout=2.0)  # must not raise
    await stopper
