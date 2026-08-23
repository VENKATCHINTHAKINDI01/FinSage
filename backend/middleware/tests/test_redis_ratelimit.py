"""Distributed rate limiter — PRD-003.

Needs a real Redis (the Lua script is the whole point; there is no pure
in-memory equivalent to fall back to). Skipped, not failed, when one is not
reachable — a CI box with no Redis service should not fail this suite, the
same policy `backend/rag/tests` uses for the embedding model.
"""

from __future__ import annotations

import time
import uuid

import pytest

pytest.importorskip("redis")

from backend.middleware.ratelimit import RateLimited
from backend.middleware.redis_ratelimit import RedisLimiter, guard_async

REDIS_URL = "redis://localhost:6379/1"  # db 1: isolated from the app's db 0


async def _client():
    import redis.asyncio as redis

    client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        await client.ping()
    except Exception:
        pytest.skip("no Redis reachable at localhost:6379")
    return client


def _key() -> str:
    return f"test:{uuid.uuid4()}"


async def test_requests_within_capacity_succeed():
    limiter = RedisLimiter(capacity=3, per_second=0.001, redis=await _client())
    key = _key()
    for _ in range(3):
        await limiter.check(key, now=time.monotonic())


async def test_the_bucket_never_grants_past_capacity():
    limiter = RedisLimiter(capacity=3, per_second=0.001, redis=await _client())
    key = _key()
    now = time.monotonic()
    for _ in range(3):
        await limiter.check(key, now=now)
    with pytest.raises(RateLimited):
        await limiter.check(key, now=now)


async def test_a_fixed_window_burst_is_not_possible():
    """Same property the in-process Limiter's test asserts: crossing a
    boundary a second later grants one more token, not another full burst."""
    limiter = RedisLimiter(capacity=60, per_second=1.0, redis=await _client())
    key = _key()
    for i in range(60):
        await limiter.check(key, now=59.0 + i * 0.001)

    granted = 0
    for _ in range(60):
        try:
            await limiter.check(key, now=60.0)
            granted += 1
        except RateLimited:
            pass
    assert granted == 1


async def test_two_concurrent_checks_never_both_grant_the_last_token():
    """The property a naive read-then-write (non-atomic) implementation would
    fail under concurrency — this is what the Lua script buys over a
    GET/refill/SET done as separate round trips."""
    import asyncio

    limiter = RedisLimiter(capacity=1, per_second=0.0001, redis=await _client())
    key = _key()
    now = time.monotonic()

    results = await asyncio.gather(
        *(limiter.check(key, now=now) for _ in range(20)),
        return_exceptions=True,
    )
    granted = sum(1 for r in results if r is None)
    assert granted == 1, f"expected exactly one grant of one token, got {granted}"


async def test_a_separate_key_has_a_separate_bucket():
    limiter = RedisLimiter(capacity=1, per_second=0.0001, redis=await _client())
    await limiter.check(_key(), now=time.monotonic())
    await limiter.check(_key(), now=time.monotonic())  # different key, not exhausted


async def test_guard_async_checks_every_applicable_limiter():
    client = await _client()
    per_user = RedisLimiter(capacity=1, per_second=0.0001, redis=client)
    per_ip = RedisLimiter(capacity=100, per_second=100, redis=client)
    now = time.monotonic()
    user_key, ip_key = _key(), _key()

    await guard_async({"user": per_user, "ip": per_ip}, {"user": user_key, "ip": ip_key}, now)
    with pytest.raises(RateLimited):
        await guard_async({"user": per_user, "ip": per_ip}, {"user": user_key, "ip": ip_key}, now)


async def test_guard_async_skips_a_missing_key():
    client = await _client()
    per_user = RedisLimiter(capacity=100, per_second=100, redis=client)
    per_ip = RedisLimiter(capacity=100, per_second=100, redis=client)
    # No "user" key present — must not raise on a limiter it has nothing to check.
    await guard_async({"user": per_user, "ip": per_ip}, {"ip": _key()}, time.monotonic())
