"""
src/extraction/redis_dedup.py — Redis-backed dedup for resumable parsing jobs.

A parsing job over a large source can be interrupted (crash, manual stop) and
restarted; without cross-run memory, every restart re-collects users already
seen. RedisDedupSet gives orchestrate_extraction_only() a shared, atomic
"have we already returned this user for this job?" check keyed by job_key,
so a resumed run only yields genuinely new users.

SADD is used for both the check and the write in one atomic round-trip:
its return value (0 = element already present, 1 = newly added) tells us
whether the user was already seen without a separate GET+SET race.
"""

from __future__ import annotations

from typing import Any

_KEY_PREFIX = "tgpool:parse-seen:"
_DEFAULT_TTL_SECONDS = 86400


class RedisDedupSet:
    """Tracks which user_ids have already been returned for a given job_key."""

    def __init__(self, redis_client: Any, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> None:
        self._redis = redis_client
        self._ttl_seconds = ttl_seconds

    async def already_seen(self, job_key: str, user_id: int) -> bool:
        """
        Returns True if user_id was already recorded for job_key, False if
        this call just recorded it for the first time.

        Refreshes the key's TTL on every newly-recorded id, so a job that's
        actively making progress keeps its dedup state alive; it only
        expires `ttl_seconds` after the last new user was seen.
        """
        key = _KEY_PREFIX + job_key
        added = await self._redis.sadd(key, user_id)
        if added:
            await self._redis.expire(key, self._ttl_seconds)
        return not added
