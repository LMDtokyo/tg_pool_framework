"""
tg_pool/accounts/warmup_policy.py — Ramp new accounts up gradually instead of using
them at full intensity from day one.

A freshly-added account sending at the same rate as a long-warmed one is a
common, avoidable cause of early bans in this space. WarmupPolicy computes,
purely from account age, both a delay multiplier (applied to AdaptiveDelay in
messaging_service.py) and a daily message cap (enforced via a per-account
RedisRateLimiter — see orchestrator.py's warmup_limiters wiring).

Account age comes from RegistryEntry.first_seen (tg_pool/accounts/account_registry.py),
which is backed by AccountRow.created_at (tg_pool/db/models.py) when persistence is
enabled — so the ramp survives restarts instead of resetting every time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from tg_pool.accounts.account_registry import AccountRegistry


def account_age_days(registry: "Optional[AccountRegistry]", phone: str) -> float:
    """
    Age of `phone` since RegistryEntry.first_seen, in days.

    Unknown (no registry, phone not registered yet, or first_seen missing)
    resolves to infinity rather than 0 -- age is unknown, not zero, so a
    missing registry never adds throttling that wasn't already there.
    """
    if registry is None:
        return float("inf")
    entry = registry.get(phone)
    if entry is None or entry.first_seen is None:
        return float("inf")
    return (datetime.now(timezone.utc) - entry.first_seen).total_seconds() / 86400.0


@dataclass(frozen=True)
class WarmupPolicy:
    """
    Linear ramp from day 0 to duration_days, then steady state.

    duration_days           — length of the ramp, in days.
    min_multiplier          — delay multiplier on day 0 (bigger = slower/safer).
    max_daily_messages_day0 — hard daily send cap on day 0.
    max_daily_messages_full — hard daily send cap once fully warmed up.
    """

    duration_days: float = 7.0
    min_multiplier: float = 3.0
    max_daily_messages_day0: int = 10
    max_daily_messages_full: int = 200

    def _progress(self, account_age_days: float) -> float:
        if self.duration_days <= 0:
            return 1.0
        return min(max(account_age_days / self.duration_days, 0.0), 1.0)

    def delay_multiplier(self, account_age_days: float) -> float:
        """1.0 once fully warmed up; min_multiplier (or higher) on day 0."""
        progress = self._progress(account_age_days)
        return self.min_multiplier - (self.min_multiplier - 1.0) * progress

    def daily_message_cap(self, account_age_days: float) -> int:
        """max_daily_messages_day0 on day 0, ramping to max_daily_messages_full."""
        progress = self._progress(account_age_days)
        span = self.max_daily_messages_full - self.max_daily_messages_day0
        return int(self.max_daily_messages_day0 + span * progress)
