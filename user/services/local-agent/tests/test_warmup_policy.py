"""tests/test_warmup_policy.py — WarmupPolicy ramp calculations."""

from datetime import datetime, timedelta, timezone

import pytest

from tg_pool.accounts.account_registry import AccountRegistry
from tg_pool.accounts.warmup_policy import WarmupPolicy, account_age_days
from tg_pool.config import AccountConfig

pytestmark = pytest.mark.unit

POLICY = WarmupPolicy(
    duration_days=7.0,
    min_multiplier=3.0,
    max_daily_messages_day0=10,
    max_daily_messages_full=200,
)


def test_day_zero_uses_min_multiplier():
    assert POLICY.delay_multiplier(0.0) == pytest.approx(3.0)


def test_fully_warmed_uses_multiplier_one():
    assert POLICY.delay_multiplier(7.0) == pytest.approx(1.0)


def test_beyond_duration_stays_at_one():
    assert POLICY.delay_multiplier(30.0) == pytest.approx(1.0)


def test_midpoint_is_halfway_between_min_and_one():
    assert POLICY.delay_multiplier(3.5) == pytest.approx(2.0)


def test_negative_age_clamped_to_day_zero():
    assert POLICY.delay_multiplier(-5.0) == POLICY.delay_multiplier(0.0)


def test_day_zero_daily_cap():
    assert POLICY.daily_message_cap(0.0) == 10


def test_fully_warmed_daily_cap():
    assert POLICY.daily_message_cap(7.0) == 200


def test_midpoint_daily_cap():
    assert POLICY.daily_message_cap(3.5) == 105


def test_zero_duration_is_always_fully_warmed():
    instant = WarmupPolicy(duration_days=0.0)
    assert instant.delay_multiplier(0.0) == pytest.approx(1.0)
    assert instant.daily_message_cap(0.0) == instant.max_daily_messages_full


# ------------------------------------------------------------------
# account_age_days
# ------------------------------------------------------------------


def test_account_age_days_is_infinite_with_no_registry():
    assert account_age_days(None, "+1") == float("inf")


async def test_account_age_days_is_infinite_for_an_unregistered_phone():
    registry = AccountRegistry()
    assert account_age_days(registry, "+1") == float("inf")


async def test_account_age_days_computes_from_first_seen():
    registry = AccountRegistry()
    await registry.register(AccountConfig(api_id=1, api_hash="hash", phone="+1"))
    entry = registry.get("+1")
    aged_entry = entry.__class__(
        account=entry.account,
        first_seen=datetime.now(timezone.utc) - timedelta(days=3),
    )
    # No public setter exists for first_seen (it's stamped once at first
    # registration) -- reach into the registry's own key to backdate it for the test.
    registry._entries[entry.account.phone] = aged_entry

    age = account_age_days(registry, "+1")
    assert 2.9 < age < 3.1
