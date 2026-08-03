"""tests/test_discovery_poller.py — AccountDiscoveryPoller sweep/loop behaviour."""

from __future__ import annotations

import asyncio

import pytest

from tg_pool.accounts.discovery_poller import AccountDiscoveryPoller
from tg_pool.monitoring.event_bus import AccountsDiscoveredEvent, EventBus

pytestmark = pytest.mark.unit


class _FakeRescan:
    """Queue of canned (loaded_phones, load_failures) results, one per call."""

    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = 0

    async def __call__(self):
        self.calls += 1
        return self._outcomes.pop(0)


class _RecordingSubscriber:
    def __init__(self):
        self.events: list = []

    def __call__(self, event) -> None:
        self.events.append(event)


async def test_sweep_publishes_nothing_when_nothing_new():
    rescan = _FakeRescan([([], [])])
    bus = EventBus()
    subscriber = _RecordingSubscriber()
    bus.subscribe(AccountsDiscoveredEvent, subscriber)
    poller = AccountDiscoveryPoller(rescan, bus, poll_interval=0.01)

    await poller._sweep_once()

    assert subscriber.events == []


async def test_sweep_publishes_a_summary_when_accounts_are_found():
    rescan = _FakeRescan([(["+7001", "+7002"], [])])
    bus = EventBus()
    subscriber = _RecordingSubscriber()
    bus.subscribe(AccountsDiscoveredEvent, subscriber)
    poller = AccountDiscoveryPoller(rescan, bus, poll_interval=0.01)

    await poller._sweep_once()

    assert len(subscriber.events) == 1
    event = subscriber.events[0]
    assert event.loaded_count == 2
    assert event.loaded_phones == ["+7001", "+7002"]
    assert event.failed_count == 0


async def test_sweep_publishes_failures_even_with_no_successes():
    rescan = _FakeRescan([([], [{"file": "bad.session", "reason": "no .json companion"}])])
    bus = EventBus()
    subscriber = _RecordingSubscriber()
    bus.subscribe(AccountsDiscoveredEvent, subscriber)
    poller = AccountDiscoveryPoller(rescan, bus, poll_interval=0.01)

    await poller._sweep_once()

    assert len(subscriber.events) == 1
    event = subscriber.events[0]
    assert event.loaded_count == 0
    assert event.failed_count == 1
    assert event.failed_reasons == ["bad.session: no .json companion"]


async def test_run_returns_immediately_if_shutdown_already_set():
    rescan = _FakeRescan([])
    bus = EventBus()
    poller = AccountDiscoveryPoller(rescan, bus, poll_interval=10.0)

    shutdown_event = asyncio.Event()
    shutdown_event.set()

    await asyncio.wait_for(poller.run(shutdown_event), timeout=1.0)

    assert rescan.calls == 0


async def test_run_sweeps_then_stops_on_shutdown():
    rescan = _FakeRescan([(["+7001"], []), ([], [])])
    bus = EventBus()
    subscriber = _RecordingSubscriber()
    bus.subscribe(AccountsDiscoveredEvent, subscriber)
    poller = AccountDiscoveryPoller(rescan, bus, poll_interval=0.05)
    shutdown_event = asyncio.Event()

    async def _stop_soon():
        await asyncio.sleep(0.1)
        shutdown_event.set()

    stopper = asyncio.create_task(_stop_soon())
    await asyncio.wait_for(poller.run(shutdown_event), timeout=2.0)
    await stopper

    assert rescan.calls >= 1
    assert len(subscriber.events) == 1


async def test_a_failing_sweep_does_not_stop_the_loop():
    class _RaisingRescan:
        def __init__(self):
            self.calls = 0

        async def __call__(self):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("disk read error")
            return (["+7001"], [])

    rescan = _RaisingRescan()
    bus = EventBus()
    subscriber = _RecordingSubscriber()
    bus.subscribe(AccountsDiscoveredEvent, subscriber)
    poller = AccountDiscoveryPoller(rescan, bus, poll_interval=0.02)
    shutdown_event = asyncio.Event()

    async def _stop_soon():
        await asyncio.sleep(0.1)
        shutdown_event.set()

    stopper = asyncio.create_task(_stop_soon())
    await asyncio.wait_for(poller.run(shutdown_event), timeout=2.0)
    await stopper

    assert rescan.calls >= 2
    assert len(subscriber.events) >= 1  # the failed first sweep must not stop later successful ones
