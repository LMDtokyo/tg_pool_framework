"""tests/test_background_writer.py — SequentialWriter ordering/durability guarantees."""

from __future__ import annotations

import asyncio

import pytest

from src.db.background_writer import SequentialWriter

pytestmark = pytest.mark.unit


async def test_submitted_write_eventually_runs():
    writer = SequentialWriter("test")
    ran = []

    async def _write():
        ran.append(1)

    writer.submit(_write)
    await writer.close()

    assert ran == [1]


async def test_writes_run_in_submission_order_even_when_first_is_slower():
    writer = SequentialWriter("test")
    order = []

    async def _slow():
        await asyncio.sleep(0.05)
        order.append("first")

    async def _fast():
        order.append("second")

    writer.submit(_slow)
    writer.submit(_fast)
    await writer.close()

    assert order == ["first", "second"]


async def test_writes_are_not_dropped_by_gc():
    """Regression: a bare `asyncio.create_task` with no retained reference can
    be garbage-collected before it runs. SequentialWriter retains its own task."""
    writer = SequentialWriter("test")
    ran = []

    async def _write():
        ran.append(1)

    writer.submit(_write)
    import gc
    gc.collect()
    await writer.close()

    assert ran == [1]


async def test_a_failing_write_does_not_stop_subsequent_writes():
    writer = SequentialWriter("test")
    ran = []

    async def _boom():
        raise RuntimeError("db down")

    async def _ok():
        ran.append(1)

    writer.submit(_boom)
    writer.submit(_ok)
    await writer.close()

    assert ran == [1]


async def test_close_drains_pending_writes_before_returning():
    writer = SequentialWriter("test")
    ran = []

    async def _write():
        await asyncio.sleep(0.01)
        ran.append(1)

    writer.submit(_write)
    writer.submit(_write)
    writer.submit(_write)
    await writer.close()

    assert ran == [1, 1, 1]


async def test_submit_after_close_raises():
    writer = SequentialWriter("test")
    await writer.close()

    with pytest.raises(RuntimeError):
        writer.submit(lambda: None)
