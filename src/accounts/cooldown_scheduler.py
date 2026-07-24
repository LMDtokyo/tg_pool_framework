"""
src/accounts/cooldown_scheduler.py — Auto-returns cooled-down accounts to the pool.

AccountState.restriction_expires (src/health_checker.py) and
AccountQuery.filter_restriction_expiring_within() (src/account_registry.py) already
expose "who is about to unfreeze" — nothing previously acted on it, so accounts
stayed excluded from the pool forever once flagged, even after Telegram lifted
the restriction. CooldownScheduler closes that loop: poll the registry, re-check
accounts whose cooldown has passed, and persist whatever the fresh check finds.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from src.accounts.account_registry import AccountRegistry
from src.accounts.health_checker import AccountStatus, HealthChecker

logger = logging.getLogger(__name__)

_COOLDOWN_STATUSES = (AccountStatus.SPAMBLOCK, AccountStatus.FROZEN, AccountStatus.FLOOD)


class CooldownScheduler:
    """
    Periodically re-checks accounts whose restriction_expires has passed.

    health_checker is expected to already be wired to an EventBus (if any) —
    check_pool_health() publishes AccountStatusEvent per account on its own,
    so this class does not publish a second time.
    """

    def __init__(
        self,
        registry: AccountRegistry,
        health_checker: HealthChecker,
        poll_interval: float = 60.0,
    ) -> None:
        self._registry = registry
        self._health_checker = health_checker
        self._poll_interval = poll_interval

    async def run(self, shutdown_event: asyncio.Event) -> None:
        """Sweep on a fixed interval until shutdown_event is set."""
        logger.info("CooldownScheduler: started (poll_interval=%.0fs)", self._poll_interval)
        while not shutdown_event.is_set():
            try:
                await self._sweep_once()
            except Exception:
                logger.exception("CooldownScheduler: sweep failed")

            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(shutdown_event.wait(), timeout=self._poll_interval)

        logger.info("CooldownScheduler: stopped")

    async def _sweep_once(self) -> None:
        expired = (
            self._registry.query()
            .filter_by_status(*_COOLDOWN_STATUSES)
            .filter_restriction_expiring_within(hours=0)
            .execute()
        )
        if not expired:
            return

        logger.info(
            "CooldownScheduler: %d account(s) past cooldown, re-checking.", len(expired)
        )
        accounts = [entry.account for entry in expired]
        report = await self._health_checker.check_pool_health(accounts, deep_check=False)

        for result in report.results:
            await self._registry.update_state(result.phone, result.account_state)
