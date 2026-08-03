"""
tg_pool/lua_storage.py — Redis Lua scripts for distributed rate-limiting and deduplication.

All Redis operations execute atomically inside a single EVAL call, preventing
race conditions between independent workers that share one Redis instance.

Token Bucket algorithm:
  Each call refills the bucket proportionally to time elapsed since the last
  access, then tries to consume `cost` tokens. If insufficient tokens remain,
  the request is rejected — no tokens are consumed on rejection.

Script contract (TOKEN_BUCKET_SCRIPT):
  KEYS[1]  bucket key       "tgpool:bucket:{pool_id}"
  KEYS[2]  blacklist key    "tgpool:blacklist:{pool_id}"
  ARGV[1]  user_id          string identifier of the recipient
  ARGV[2]  capacity         integer — max tokens the bucket can hold
  ARGV[3]  refill_rate      float  — tokens added per second
  ARGV[4]  now              float  — current unix timestamp (time.time())
  ARGV[5]  cost             integer — tokens consumed per send (normally 1)
  ARGV[6]  ttl              integer — Redis key TTL in seconds

Returns: Redis array [allowed, reason]
  allowed  1 (permit) or 0 (reject)
  reason   "ok" | "blacklisted" | "rate_limited"
"""

from __future__ import annotations

import logging
import time
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lua scripts — stored as module-level constants so they can be registered
# once per Redis connection and reused via SHA (EVALSHA).
# ---------------------------------------------------------------------------

TOKEN_BUCKET_SCRIPT = """\
local bucket_key    = KEYS[1]
local blacklist_key = KEYS[2]

local user_id    = ARGV[1]
local capacity   = tonumber(ARGV[2])
local rate       = tonumber(ARGV[3])
local now        = tonumber(ARGV[4])
local cost       = tonumber(ARGV[5])
local ttl        = tonumber(ARGV[6])

-- Step 1: O(1) blacklist check before touching the bucket
if redis.call("SISMEMBER", blacklist_key, user_id) == 1 then
    return {0, "blacklisted"}
end

-- Step 2: Read current bucket state (defaults: full bucket, now as seed)
local raw     = redis.call("HMGET", bucket_key, "tokens", "last_refill")
local tokens      = tonumber(raw[1]) or capacity
local last_refill = tonumber(raw[2]) or now

-- Step 3: Refill proportionally to elapsed time
local elapsed = math.max(0, now - last_refill)
tokens = math.min(capacity, tokens + elapsed * rate)

-- Step 4: Consume or reject
if tokens < cost then
    redis.call("HMSET", bucket_key, "tokens", tokens, "last_refill", now)
    redis.call("EXPIRE", bucket_key, ttl)
    return {0, "rate_limited"}
end

tokens = tokens - cost
redis.call("HMSET", bucket_key, "tokens", tokens, "last_refill", now)
redis.call("EXPIRE", bucket_key, ttl)
return {1, "ok"}
"""

BLACKLIST_ADD_SCRIPT = """\
redis.call("SADD", KEYS[1], ARGV[1])
return 1
"""

BLACKLIST_REMOVE_SCRIPT = """\
redis.call("SREM", KEYS[1], ARGV[1])
return 1
"""


# ---------------------------------------------------------------------------
# RedisRateLimiter — high-level async wrapper
# ---------------------------------------------------------------------------

class RedisRateLimiter:
    """
    Distributed Token Bucket rate limiter backed by Redis + Lua.

    Designed for redis.asyncio.Redis (async client). Scripts are registered
    once on construction; subsequent calls use EVALSHA (faster than EVAL).

    Usage:
        import redis.asyncio as aioredis
        r = aioredis.from_url("redis://localhost")
        limiter = RedisRateLimiter(r, pool_id="prod")

        allowed, reason = await limiter.check_and_consume("username123")
        if not allowed:
            logger.info("Skip %s: %s", user_id, reason)
    """

    def __init__(
        self,
        redis_client,
        pool_id: str = "default",
        capacity: int = 100,
        refill_rate: float = 1.0,
        cost: int = 1,
        bucket_ttl: int = 3600,
        fail_mode: str = "open",
    ) -> None:
        if fail_mode not in ("open", "closed"):
            raise ValueError(f"fail_mode must be 'open' or 'closed', got {fail_mode!r}")

        self._redis = redis_client
        self._bucket_key = f"tgpool:bucket:{pool_id}"
        self._blacklist_key = f"tgpool:blacklist:{pool_id}"
        self._capacity = capacity
        self._refill_rate = refill_rate
        self._cost = cost
        self._bucket_ttl = bucket_ttl
        self._fail_mode = fail_mode

        # Register scripts at construction time → reuse via SHA
        self._script_bucket = redis_client.register_script(TOKEN_BUCKET_SCRIPT)
        self._script_bl_add = redis_client.register_script(BLACKLIST_ADD_SCRIPT)
        self._script_bl_remove = redis_client.register_script(BLACKLIST_REMOVE_SCRIPT)

    async def check_and_consume(self, user_id: str) -> Tuple[bool, str]:
        """
        Checks the blacklist, then atomically checks rate limit and consumes
        one token.

        The blacklist is a safety control (reported/opt-out/blocked users),
        not a throughput knob, so it always fails closed — a Redis outage
        during the blacklist check blocks the send rather than silently
        bypassing it, regardless of fail_mode.

        fail_mode only governs the token-bucket portion on Redis errors:
          "open"   (default) — returns (True, "redis_error"): a transient
                    Redis outage does not halt the entire send pipeline.
          "closed" — returns (False, "redis_error"): sends are blocked until
                    Redis recovers, trading availability for safety.
        """
        try:
            if await self._redis.sismember(self._blacklist_key, user_id):
                return False, "blacklisted"
        except Exception as exc:
            logger.error("Redis blacklist check failed (%s) — failing closed.", exc)
            return False, "redis_error"

        try:
            result = await self._script_bucket(
                keys=[self._bucket_key, self._blacklist_key],
                args=[
                    user_id,
                    str(self._capacity),
                    str(self._refill_rate),
                    f"{time.time():.6f}",
                    str(self._cost),
                    str(self._bucket_ttl),
                ],
            )
            allowed = bool(int(result[0]))
            reason = result[1].decode() if isinstance(result[1], bytes) else str(result[1])
            return allowed, reason

        except Exception as exc:
            allowed = self._fail_mode == "open"
            logger.error(
                "Redis rate limit check failed (%s) — failing %s.", exc, self._fail_mode
            )
            return allowed, "redis_error"

    async def blacklist_add(self, user_id: str) -> None:
        """Atomically adds user_id to the shared blacklist."""
        await self._script_bl_add(keys=[self._blacklist_key], args=[user_id])
        logger.info("Blacklisted: %s", user_id)

    async def blacklist_remove(self, user_id: str) -> None:
        """Removes user_id from the shared blacklist."""
        await self._script_bl_remove(keys=[self._blacklist_key], args=[user_id])
        logger.info("Un-blacklisted: %s", user_id)
