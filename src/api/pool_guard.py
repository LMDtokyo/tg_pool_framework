"""
src/api/pool_guard.py — Mutual exclusion between jobs that share the account pool.

CampaignManager and ParsingManager both build a ClientPool over the same
`primary` accounts loaded once in app.py's lifespan(). Telethon's default
SQLiteSession requires exclusive access to a .session file from a single
connection -- if a campaign and a parsing job connected the same accounts
concurrently, both would try to open the same .session files at once.
PoolAccessGuard gives both managers a shared, explicit "who's using the
pool right now" check before they start.
"""

from __future__ import annotations

from typing import Optional


class PoolBusyError(RuntimeError):
    """Raised by PoolAccessGuard.try_acquire() when another job already holds the pool."""


class PoolAccessGuard:
    """Tracks which job (if any) currently holds exclusive use of the account pool."""

    def __init__(self) -> None:
        self._holder: Optional[str] = None

    @property
    def current_holder(self) -> Optional[str]:
        return self._holder

    def try_acquire(self, holder: str) -> None:
        """Raises PoolBusyError naming the current holder if the pool is already in use."""
        if self._holder is not None and self._holder != holder:
            raise PoolBusyError(
                f"Account pool is busy: '{self._holder}' is currently using it."
            )
        self._holder = holder

    def release(self, holder: str) -> None:
        """No-op if a different holder (or nothing) currently holds it."""
        if self._holder == holder:
            self._holder = None
