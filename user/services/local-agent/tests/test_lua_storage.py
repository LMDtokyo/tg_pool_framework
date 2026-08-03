"""
tests/test_lua_storage.py — Tests for tg_pool/lua_storage.py.

Two test layers:

  Layer 1 — Lua script correctness (fakeredis):
    Uses fakeredis.FakeRedis (sync, executes real Lua via lupa).
    Tests the actual Token Bucket logic and blacklist semantics without a
    real Redis instance. Install: pip install fakeredis[lua]

  Layer 2 — RedisRateLimiter wrapper (AsyncMock):
    Verifies that check_and_consume / blacklist_add / blacklist_remove call
    the registered scripts with the correct keys and argument structure.
    Does not re-test Lua semantics — that is Layer 1's responsibility.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, call

import pytest
import fakeredis

from tg_pool.messaging.lua_storage import (
    BLACKLIST_ADD_SCRIPT,
    BLACKLIST_REMOVE_SCRIPT,
    TOKEN_BUCKET_SCRIPT,
    RedisRateLimiter,
)


# ---------------------------------------------------------------------------
# Helpers for Layer 1
# ---------------------------------------------------------------------------

BUCKET_KEY = "test:bucket"
BLACKLIST_KEY = "test:blacklist"
CAPACITY = 5
RATE = 1.0       # 1 token/second
TTL = 3600


def run_bucket(r: fakeredis.FakeRedis, user: str, now: float, cost: int = 1) -> list:
    """Calls TOKEN_BUCKET_SCRIPT synchronously via fakeredis."""
    script = r.register_script(TOKEN_BUCKET_SCRIPT)
    return script(
        keys=[BUCKET_KEY, BLACKLIST_KEY],
        args=[user, str(CAPACITY), str(RATE), f"{now:.6f}", str(cost), str(TTL)],
    )


# ---------------------------------------------------------------------------
# Layer 1: Lua script — Token Bucket
# ---------------------------------------------------------------------------

class TestTokenBucketLua:
    def test_fresh_bucket_is_allowed(self):
        r = fakeredis.FakeRedis()
        result = run_bucket(r, "alice", now=1000.0)
        assert result[0] == 1
        assert result[1] == b"ok"

    def test_bucket_drains_to_zero(self):
        """CAPACITY consecutive requests should all succeed."""
        r = fakeredis.FakeRedis()
        for _ in range(CAPACITY):
            result = run_bucket(r, "alice", now=1000.0)
            assert result[0] == 1, "Should be allowed while tokens remain"

    def test_exhausted_bucket_is_rejected(self):
        """One more request after draining the bucket must be rate_limited."""
        r = fakeredis.FakeRedis()
        for _ in range(CAPACITY):
            run_bucket(r, "alice", now=1000.0)

        result = run_bucket(r, "alice", now=1000.0)  # same timestamp → no refill
        assert result[0] == 0
        assert result[1] == b"rate_limited"

    def test_bucket_refills_over_time(self):
        """
        Drain the bucket completely, then advance time so tokens refill.
        With RATE=1.0 and elapsed=CAPACITY seconds, the bucket should be
        full again and the next request must succeed.
        """
        r = fakeredis.FakeRedis()
        for _ in range(CAPACITY):
            run_bucket(r, "alice", now=1000.0)

        # Time advances by CAPACITY seconds → CAPACITY new tokens
        result = run_bucket(r, "alice", now=1000.0 + CAPACITY)
        assert result[0] == 1
        assert result[1] == b"ok"

    def test_high_cost_request_rejected_when_insufficient(self):
        """A request with cost > available tokens must be rejected."""
        r = fakeredis.FakeRedis()
        # Consume all but 1 token
        for _ in range(CAPACITY - 1):
            run_bucket(r, "alice", now=1000.0)

        # Request cost=2 but only 1 token left
        script = r.register_script(TOKEN_BUCKET_SCRIPT)
        result = script(
            keys=[BUCKET_KEY, BLACKLIST_KEY],
            args=["alice", str(CAPACITY), str(RATE), "1000.0", "2", str(TTL)],
        )
        assert result[0] == 0
        assert result[1] == b"rate_limited"

    def test_pool_bucket_is_shared_across_users(self):
        """
        The token bucket is POOL-level, not per-user.
        All user_ids draw from the same shared token pool.
        Draining the pool via "alice" will also block "bob".
        Per-user blocking is handled by the blacklist, not the bucket.
        """
        r = fakeredis.FakeRedis()
        for _ in range(CAPACITY):
            run_bucket(r, "alice", now=1000.0)

        # Pool exhausted — both alice and bob are rate-limited
        assert run_bucket(r, "alice", now=1000.0)[0] == 0
        assert run_bucket(r, "bob", now=1000.0)[0] == 0

    def test_bucket_key_has_ttl_set(self):
        """EXPIRE must be set on the bucket key after every call."""
        r = fakeredis.FakeRedis()
        run_bucket(r, "alice", now=1000.0)
        ttl_remaining = r.ttl(BUCKET_KEY)
        assert 0 < ttl_remaining <= TTL


# ---------------------------------------------------------------------------
# Layer 1: Lua script — Blacklist
# ---------------------------------------------------------------------------

class TestBlacklistLua:
    def test_blacklisted_user_is_rejected_before_bucket(self):
        r = fakeredis.FakeRedis()
        # Add to blacklist
        bl_script = r.register_script(BLACKLIST_ADD_SCRIPT)
        bl_script(keys=[BLACKLIST_KEY], args=["evil_user"])

        # Token bucket is full — but blacklist takes precedence
        result = run_bucket(r, "evil_user", now=1000.0)
        assert result[0] == 0
        assert result[1] == b"blacklisted"

    def test_non_blacklisted_user_passes(self):
        r = fakeredis.FakeRedis()
        bl_script = r.register_script(BLACKLIST_ADD_SCRIPT)
        bl_script(keys=[BLACKLIST_KEY], args=["evil_user"])

        result = run_bucket(r, "good_user", now=1000.0)
        assert result[0] == 1

    def test_remove_from_blacklist(self):
        r = fakeredis.FakeRedis()
        bl_add = r.register_script(BLACKLIST_ADD_SCRIPT)
        bl_rem = r.register_script(BLACKLIST_REMOVE_SCRIPT)

        bl_add(keys=[BLACKLIST_KEY], args=["reformed_user"])
        bl_rem(keys=[BLACKLIST_KEY], args=["reformed_user"])

        result = run_bucket(r, "reformed_user", now=1000.0)
        assert result[0] == 1


# ---------------------------------------------------------------------------
# Layer 2: RedisRateLimiter wrapper (AsyncMock, no Lua execution)
# ---------------------------------------------------------------------------

def make_limiter_with_mock_redis(fail_mode: str = "open"):
    """
    Builds a RedisRateLimiter backed by a mock async Redis client.

    The registered scripts are replaced with AsyncMocks so we can
    inspect call arguments without executing Lua. `sismember` (the
    pre-flight blacklist check) defaults to "not blacklisted" (0).
    """
    mock_redis = MagicMock()
    mock_redis.sismember = AsyncMock(return_value=0)

    mock_bucket_script = AsyncMock(return_value=[1, b"ok"])
    mock_bl_add_script = AsyncMock(return_value=1)
    mock_bl_rem_script = AsyncMock(return_value=1)

    mock_redis.register_script.side_effect = [
        mock_bucket_script,
        mock_bl_add_script,
        mock_bl_rem_script,
    ]

    limiter = RedisRateLimiter(
        mock_redis,
        pool_id="test",
        capacity=10,
        refill_rate=2.0,
        cost=1,
        bucket_ttl=600,
        fail_mode=fail_mode,
    )
    return limiter, mock_bucket_script, mock_bl_add_script, mock_bl_rem_script, mock_redis


class TestRedisRateLimiterWrapper:
    async def test_check_and_consume_returns_allowed_true_on_ok(self):
        limiter, mock_script, _, __, ___ = make_limiter_with_mock_redis()
        mock_script.return_value = [1, b"ok"]

        allowed, reason = await limiter.check_and_consume("alice")

        assert allowed is True
        assert reason == "ok"

    async def test_check_and_consume_returns_false_on_rate_limited(self):
        limiter, mock_script, _, __, ___ = make_limiter_with_mock_redis()
        mock_script.return_value = [0, b"rate_limited"]

        allowed, reason = await limiter.check_and_consume("alice")

        assert allowed is False
        assert reason == "rate_limited"

    async def test_check_and_consume_returns_false_on_blacklisted(self):
        """Blacklisted via the bucket script's own internal check (defense in depth)."""
        limiter, mock_script, _, __, ___ = make_limiter_with_mock_redis()
        mock_script.return_value = [0, b"blacklisted"]

        allowed, reason = await limiter.check_and_consume("evil")

        assert allowed is False
        assert reason == "blacklisted"

    async def test_check_and_consume_returns_false_on_blacklisted_via_preflight_check(self):
        """The sismember pre-flight check short-circuits before the bucket script runs."""
        limiter, mock_script, _, __, mock_redis = make_limiter_with_mock_redis()
        mock_redis.sismember.return_value = 1

        allowed, reason = await limiter.check_and_consume("evil")

        assert allowed is False
        assert reason == "blacklisted"
        mock_script.assert_not_called()

    async def test_check_and_consume_fails_closed_on_blacklist_check_error_even_in_fail_open_mode(self):
        """
        The blacklist is a safety control, not a throughput knob: a Redis
        error while checking it must block the send even when fail_mode is
        "open" — fail_mode only governs the token-bucket portion.
        """
        limiter, mock_script, _, __, mock_redis = make_limiter_with_mock_redis(fail_mode="open")
        mock_redis.sismember.side_effect = ConnectionError("Redis down")

        allowed, reason = await limiter.check_and_consume("user1")

        assert allowed is False
        assert reason == "redis_error"
        mock_script.assert_not_called()

    async def test_check_and_consume_correct_keys_passed(self):
        """Verify bucket_key and blacklist_key are constructed from pool_id."""
        limiter, mock_script, _, __, ___ = make_limiter_with_mock_redis()

        await limiter.check_and_consume("user1")

        _, kwargs = mock_script.call_args
        keys = kwargs.get("keys") or mock_script.call_args[0][0]
        assert keys[0] == "tgpool:bucket:test"
        assert keys[1] == "tgpool:blacklist:test"

    async def test_check_and_consume_user_id_in_args(self):
        limiter, mock_script, _, __, ___ = make_limiter_with_mock_redis()

        await limiter.check_and_consume("target_user")

        _, kwargs = mock_script.call_args
        args = kwargs.get("args") or mock_script.call_args[0][1]
        assert args[0] == "target_user"

    async def test_check_and_consume_fails_open_on_redis_error(self):
        """A Redis exception from the bucket script must not crash the pipeline — fails open."""
        limiter, mock_script, _, __, ___ = make_limiter_with_mock_redis()
        mock_script.side_effect = ConnectionError("Redis down")

        allowed, reason = await limiter.check_and_consume("user1")

        assert allowed is True   # fail open
        assert reason == "redis_error"

    async def test_check_and_consume_fails_closed_when_configured(self):
        """fail_mode='closed' blocks sends instead of letting them through."""
        limiter, mock_script, _, __, ___ = make_limiter_with_mock_redis(fail_mode="closed")
        mock_script.side_effect = ConnectionError("Redis down")

        allowed, reason = await limiter.check_and_consume("user1")

        assert allowed is False
        assert reason == "redis_error"

    def test_rejects_invalid_fail_mode(self):
        mock_redis = MagicMock()
        mock_redis.register_script.side_effect = [AsyncMock(), AsyncMock(), AsyncMock()]
        with pytest.raises(ValueError):
            RedisRateLimiter(mock_redis, fail_mode="sideways")

    async def test_blacklist_add_calls_script_with_correct_args(self):
        limiter, _, mock_bl_add, __, ___ = make_limiter_with_mock_redis()

        await limiter.blacklist_add("spammer")

        _, kwargs = mock_bl_add.call_args
        keys = kwargs.get("keys") or mock_bl_add.call_args[0][0]
        args = kwargs.get("args") or mock_bl_add.call_args[0][1]
        assert keys[0] == "tgpool:blacklist:test"
        assert args[0] == "spammer"

    async def test_blacklist_remove_calls_script_with_correct_args(self):
        limiter, _, __, mock_bl_rem, ___ = make_limiter_with_mock_redis()

        await limiter.blacklist_remove("reformed")

        _, kwargs = mock_bl_rem.call_args
        keys = kwargs.get("keys") or mock_bl_rem.call_args[0][0]
        args = kwargs.get("args") or mock_bl_rem.call_args[0][1]
        assert keys[0] == "tgpool:blacklist:test"
        assert args[0] == "reformed"
