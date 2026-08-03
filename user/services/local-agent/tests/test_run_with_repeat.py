"""tests/test_run_with_repeat.py — Tests for orchestrator.run_with_repeat(), the repeat-whole-campaign-cycle-after-N-hours wrapper."""

from __future__ import annotations

import asyncio

from tg_pool.messaging.messaging_service import BatchReport
from tg_pool.orchestrator import run_with_repeat


async def test_no_repeat_runs_once():
    call_count = 0

    async def run_once():
        nonlocal call_count
        call_count += 1
        return BatchReport(total=1, succeeded=1)

    report = await run_with_repeat(run_once, shutdown_event=None, repeat_every_hours=None)

    assert call_count == 1
    assert report.succeeded == 1


async def test_no_shutdown_event_still_runs_once_without_repeat():
    call_count = 0

    async def run_once():
        nonlocal call_count
        call_count += 1
        return BatchReport(total=1, succeeded=1)

    report = await run_with_repeat(run_once, shutdown_event=None, repeat_every_hours=None)

    assert call_count == 1
    assert report.total == 1


async def test_stops_immediately_when_shutdown_already_set_after_first_cycle():
    call_count = 0
    shutdown_event = asyncio.Event()

    async def run_once():
        nonlocal call_count
        call_count += 1
        shutdown_event.set()
        return BatchReport(total=1, succeeded=1)

    report = await run_with_repeat(run_once, shutdown_event, repeat_every_hours=1.0)

    assert call_count == 1
    assert report.total == 1


async def test_merges_reports_across_repeat_cycles():
    call_count = 0
    shutdown_event = asyncio.Event()

    async def run_once():
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            shutdown_event.set()
        return BatchReport(total=1, succeeded=1, sent_recipients={f"user{call_count}"})

    # Tiny repeat interval: the between-cycle wait_for(..., timeout=...) elapses on
    # its own (TimeoutError, caught) rather than the event unblocking it -- the
    # event is only set from inside run_once(), which can't fire again until the
    # sleep between cycle 1 and cycle 2 actually completes.
    report = await asyncio.wait_for(
        run_with_repeat(run_once, shutdown_event, repeat_every_hours=0.05 / 3600),
        timeout=5.0,
    )

    assert call_count == 2
    assert report.total == 2
    assert report.succeeded == 2
    assert report.sent_recipients == {"user1", "user2"}


async def test_wakes_early_from_sleep_when_shutdown_fires_mid_wait():
    call_count = 0
    shutdown_event = asyncio.Event()

    async def run_once():
        nonlocal call_count
        call_count += 1
        return BatchReport(total=1, succeeded=1)

    async def _fire_shutdown_shortly():
        await asyncio.sleep(0.05)
        shutdown_event.set()

    firer = asyncio.create_task(_fire_shutdown_shortly())
    # repeat_every_hours=10s worth -- if the sleep didn't wake early on the
    # event, this wait_for(timeout=2.0) would time out well before it elapses.
    report = await asyncio.wait_for(
        run_with_repeat(run_once, shutdown_event, repeat_every_hours=10 / 3600),
        timeout=2.0,
    )
    await firer

    assert call_count == 1
    assert report.total == 1
