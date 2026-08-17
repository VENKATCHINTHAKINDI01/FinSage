"""Distributed token bucket over Redis — PRD-003.

The in-process `Limiter` in `ratelimit.py` is correct for one running
instance and wrong the moment there is more than one, because each instance
would enforce the stated rate independently (N instances grant N times the
rate). This is the fix: the same refill-then-check-then-decrement arithmetic,
made atomic across instances with a single Lua script per request so two
concurrent refills can never both read the same tokens.

Verified against a live `redis:7-alpine` container (docker-compose), not
just unit-tested against the algorithm in isolation — see
`backend/middleware/tests/test_redis_ratelimit.py`, which is skipped rather
than failed when no Redis is reachable.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.middleware.ratelimit import RateLimited

# KEYS[1] = bucket key
# ARGV[1] = capacity, ARGV[2] = per_second, ARGV[3] = now, ARGV[4] = cost
#
# Mirrors Bucket._refill/.take in ratelimit.py exactly: `updated_at` absent
# means "never used", refills to full capacity rather than zero — the same
# sentinel-vs-zero distinction that module's docstring calls out.
_TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local per_second = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])

local data = redis.call('HMGET', key, 'tokens', 'updated_at')
local tokens = tonumber(data[1])
local updated_at = tonumber(data[2])

if tokens == nil then
  tokens = capacity
else
  local elapsed = math.max(0, now - updated_at)
  tokens = math.min(capacity, tokens + elapsed * per_second)
end

local granted = 0
if tokens >= cost then
  tokens = tokens - cost
  granted = 1
end

redis.call('HMSET', key, 'tokens', tostring(tokens), 'updated_at', tostring(now))
-- A bucket nobody has drawn from in an hour is not worth the memory; the
-- next request just sees no key, i.e. `tokens == nil`, i.e. a full refill.
redis.call('EXPIRE', key, 3600)

if granted == 1 then
  return {1, "0"}
end
local deficit = cost - tokens
return {0, tostring(deficit)}
"""


@dataclass(slots=True)
class RedisLimiter:
    """Same shape as `Limiter.check`, but atomic across every process sharing
    this Redis, and async because a real network call is behind it."""

    capacity: float
    per_second: float
    redis: object          # redis.asyncio.Redis — untyped to avoid a hard import here
    prefix: str = "ratelimit"
    _script_sha: str | None = None

    async def check(self, key: str, now: float, cost: float = 1.0) -> None:
        granted, deficit = await self.redis.eval(
            _TOKEN_BUCKET_LUA, 1, f"{self.prefix}:{key}",
            self.capacity, self.per_second, now, cost,
        )
        if not int(granted):
            deficit_f = float(deficit)
            raise RateLimited(
                deficit_f / self.per_second if self.per_second else 3600.0,
                f"bucket empty: {deficit_f:.2f} of {cost} tokens short.",
            )


async def guard_async(limiters: dict[str, RedisLimiter], keys: dict[str, str], now: float) -> None:
    """Async twin of `ratelimit.guard` — every applicable limit, not just the
    first that matches, same as the in-process version and for the same
    reason (a per-user limit alone is evaded by registering more accounts)."""
    for name, limiter in limiters.items():
        key = keys.get(name)
        if key:
            await limiter.check(key, now)


__all__ = ["RedisLimiter", "guard_async"]
