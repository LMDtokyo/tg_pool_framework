"""
src/db/background_writer.py — Sequential fire-and-forget background writer.

Used by AccountRegistry and CampaignRecorder to persist durable-store writes
without blocking their hot path. Fixes the two failure modes of a bare
`asyncio.create_task(...)` per write: the task can be garbage-collected
before it runs (nothing holds a strong reference to it), and independent
concurrent tasks for the same key can commit to the database out of order.
A single retained consumer task processes writes strictly in submission
order; close() drains it before process exit so the final batch isn't lost.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

_CLOSE_SENTINEL = object()


class SequentialWriter:
    """Runs submitted async write callables one at a time, in submission order."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._queue: "asyncio.Queue" = asyncio.Queue()
        self._task: Optional[asyncio.Task] = asyncio.create_task(
            self._run(), name=f"{name}-writer"
        )

    def submit(self, write: Callable[[], Awaitable[None]]) -> None:
        """Fire-and-forget enqueue — never blocks the caller."""
        if self._task is None:
            raise RuntimeError(f"{self._name}: writer is closed")
        self._queue.put_nowait(write)

    async def _run(self) -> None:
        while True:
            item = await self._queue.get()
            if item is _CLOSE_SENTINEL:
                self._queue.task_done()
                return
            try:
                await item()
            except Exception:
                logger.exception("%s: background write failed", self._name)
            finally:
                self._queue.task_done()

    async def close(self) -> None:
        """Drain queued writes and stop the consumer. Await before process exit."""
        if self._task is None:
            return
        await self._queue.put(_CLOSE_SENTINEL)
        await self._task
        self._task = None
