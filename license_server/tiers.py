"""
license_server/tiers.py — Subscription tiers and their durations.

The expiry clock starts at first activation, not at key generation, so keys
sitting unsold in inventory don't expire on the shelf.
"""

from __future__ import annotations

from datetime import timedelta
from enum import Enum


class Tier(str, Enum):
    WEEK = "week"
    MONTH = "month"
    HALF_YEAR = "half_year"
    YEAR = "year"


_DURATIONS: dict[Tier, timedelta] = {
    Tier.WEEK: timedelta(days=7),
    Tier.MONTH: timedelta(days=30),
    Tier.HALF_YEAR: timedelta(days=182),
    Tier.YEAR: timedelta(days=365),
}


def duration_for(tier: Tier) -> timedelta:
    return _DURATIONS[tier]
