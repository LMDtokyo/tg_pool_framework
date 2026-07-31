"""
src/accounts/discovery_poller.py — Periodically checks the accounts/tdata
directories for newly dropped account files/folders, loads whatever it can,
and publishes an AccountsDiscoveredEvent summarizing what happened.

Without this, an operator who copies a purchased account base into
Data\\Accounts only sees it once they open (or refresh) the Accounts tab --
this makes the same rescan happen on a timer, so the launcher can prompt
them proactively instead.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Awaitable, Callable, List, Tuple

from src.monitoring.event_bus import AccountsDiscoveredEvent, EventBus

logger = logging.getLogger(__name__)

RescanFn = Callable[[], Awaitable[Tuple[List[str], List[dict]]]]


class AccountDiscoveryPoller:
    """Sweeps on a fixed interval until shutdown_event is set (same shape as
    CooldownScheduler/ScheduledCampaignManager's run loops)."""

    def __init__(self, rescan: RescanFn, event_bus: EventBus, poll_interval: float = 30.0) -> None:
        self._rescan = rescan
        self._event_bus = event_bus
        self._poll_interval = poll_interval

    async def run(self, shutdown_event: asyncio.Event) -> None:
        logger.info("AccountDiscoveryPoller: started (poll_interval=%.0fs)", self._poll_interval)
        while not shutdown_event.is_set():
            try:
                await self._sweep_once()
            except Exception:
                logger.exception("AccountDiscoveryPoller: sweep failed")

            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(shutdown_event.wait(), timeout=self._poll_interval)

        logger.info("AccountDiscoveryPoller: stopped")

    async def _sweep_once(self) -> None:
        loaded_phones, load_failures = await self._rescan()
        if not loaded_phones and not load_failures:
            return

        logger.info(
            "AccountDiscoveryPoller: %d new account(s), %d failure(s).",
            len(loaded_phones), len(load_failures),
        )
        await self._event_bus.publish(
            AccountsDiscoveredEvent(
                loaded_count=len(loaded_phones),
                loaded_phones=loaded_phones,
                failed_count=len(load_failures),
                failed_reasons=[f"{item['file']}: {item['reason']}" for item in load_failures],
            )
        )
