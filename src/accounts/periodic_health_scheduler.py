"""
src/accounts/periodic_health_scheduler.py — Recurring full-pool health recheck.

CooldownScheduler (src/accounts/cooldown_scheduler.py) only rechecks accounts
already flagged SPAMBLOCK/FROZEN/FLOOD whose restriction has expired -- it
never re-examines an account currently marked ALIVE, so a fresh ban goes
unnoticed until the next full run/restart. PeriodicHealthScheduler closes
that gap: it rechecks every account in the pool on a fixed interval,
regardless of current status.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import List

from src.accounts.account_registry import AccountRegistry
from src.accounts.health_checker import HealthChecker
from src.config import AccountConfig

logger = logging.getLogger(__name__)


class PeriodicHealthScheduler:
    """Rechecks every account in `accounts` on a fixed interval."""

    def __init__(
        self,
        accounts: List[AccountConfig],
        registry: AccountRegistry,
        health_checker: HealthChecker,
        poll_interval: float = 1800.0,
        deep_check: bool = False,
    ) -> None:
        self._accounts = accounts
        self._registry = registry
        self._health_checker = health_checker
        self._poll_interval = poll_interval
        self._deep_check = deep_check

    async def run(self, shutdown_event: asyncio.Event) -> None:
        """
        Wait poll_interval, sweep, repeat -- until shutdown_event is set.

        Waits before the first sweep rather than sweeping immediately (unlike
        CooldownScheduler): this scheduler typically starts right after the
        pipeline's own startup health check, so an immediate recheck would
        just repeat work already done this run.
        """
        logger.info(
            "PeriodicHealthScheduler: started (poll_interval=%.0fs, %d accounts)",
            self._poll_interval, len(self._accounts),
        )
        while not shutdown_event.is_set():
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(shutdown_event.wait(), timeout=self._poll_interval)
            if shutdown_event.is_set():
                break
            try:
                await self._sweep_once()
            except Exception:
                logger.exception("PeriodicHealthScheduler: sweep failed")

        logger.info("PeriodicHealthScheduler: stopped")

    async def _sweep_once(self) -> None:
        if not self._accounts:
            return
        logger.info("PeriodicHealthScheduler: rechecking %d accounts.", len(self._accounts))
        report = await self._health_checker.check_pool_health(
            self._accounts, deep_check=self._deep_check
        )
        for result in report.results:
            await self._registry.update_state(result.phone, result.account_state)
        logger.info("PeriodicHealthScheduler: %s", report.summary())
