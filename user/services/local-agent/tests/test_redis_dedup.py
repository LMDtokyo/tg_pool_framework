"""tests/test_redis_dedup.py — Tests for tg_pool/extraction/redis_dedup.py (fakeredis, async)."""

from __future__ import annotations

import fakeredis.aioredis as fakeredis_aio
import pytest

from tg_pool.extraction.redis_dedup import RedisDedupSet

pytestmark = pytest.mark.unit


@pytest.fixture
def redis_client():
    return fakeredis_aio.FakeRedis()


async def test_first_sighting_is_not_already_seen(redis_client):
    dedup = RedisDedupSet(redis_client)

    assert await dedup.already_seen("job1", 111) is False


async def test_second_sighting_of_same_user_is_already_seen(redis_client):
    dedup = RedisDedupSet(redis_client)

    await dedup.already_seen("job1", 111)

    assert await dedup.already_seen("job1", 111) is True


async def test_different_users_are_independent(redis_client):
    dedup = RedisDedupSet(redis_client)

    await dedup.already_seen("job1", 111)

    assert await dedup.already_seen("job1", 222) is False


async def test_different_job_keys_are_independent(redis_client):
    dedup = RedisDedupSet(redis_client)

    await dedup.already_seen("job1", 111)

    assert await dedup.already_seen("job2", 111) is False


async def test_ttl_set_on_first_insert(redis_client):
    dedup = RedisDedupSet(redis_client, ttl_seconds=3600)

    await dedup.already_seen("job1", 111)

    ttl = await redis_client.ttl("tgpool:parse-seen:job1")
    assert 0 < ttl <= 3600


async def test_resumed_job_skips_previously_seen_users(redis_client):
    """Simulates an interrupted-then-resumed job: same job_key, same users."""
    dedup = RedisDedupSet(redis_client)
    first_run_users = [1, 2, 3]
    for user_id in first_run_users:
        assert await dedup.already_seen("resumable-job", user_id) is False

    second_run_users = [2, 3, 4, 5]
    results = {
        user_id: await dedup.already_seen("resumable-job", user_id)
        for user_id in second_run_users
    }

    assert results == {2: True, 3: True, 4: False, 5: False}
