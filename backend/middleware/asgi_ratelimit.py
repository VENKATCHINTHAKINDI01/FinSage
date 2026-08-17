"""FastAPI wiring for `backend.middleware.ratelimit` — PRD-003.

The pure token-bucket logic in `ratelimit.py` (`Limiter`, `guard`) is fully
tested against wall-clock-independent `now` values. This module is the thin,
literally-untestable-any-other-way layer on top: reading the real clock, the
real request, and turning a `RateLimited` into a real 429.

Distributed when Redis is reachable, per-process otherwise
-------------------------------------------------------------
`Limiter` keeps its buckets in an in-process dict — correct for one running
instance, wrong the moment there is more than one, because each instance
would enforce the limit independently (N instances grant N times the stated
rate). `RedisLimiter` (`backend/middleware/redis_ratelimit.py`) fixes that
with an atomic refill-check-decrement Lua script, verified against a live
Redis under concurrent requests in `test_redis_ratelimit.py` — a decrement
that is not provably atomic is worse than the in-process gap it would claim
to close.

This middleware prefers Redis and falls back to the in-process limiter if a
client cannot be obtained — consistent with "fails OPEN" below: a Redis
outage degrades to per-process enforcement, not to no enforcement, and
definitely not to a 500.

Fails OPEN by design (module docstring in `ratelimit.py`): only `RateLimited`
short-circuits the request. Any other exception here is logged and swallowed
— a bug in the limiter must not become an outage.
"""

from __future__ import annotations

import inspect
import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from backend.middleware.ratelimit import Limiter, RateLimited
from backend.middleware.redis_ratelimit import RedisLimiter
from backend.security.jwt_handler import verify_token

logger = logging.getLogger(__name__)

# Conservative defaults: generous enough not to bother a real user clicking
# around, tight enough to blunt a scripted hammering of the API. Burst is the
# bucket capacity; per_second is the sustained refill rate. Shared between the
# in-process and Redis-backed limiters so a failover does not also change the
# effective rate.
CAPACITY_PER_USER, RATE_PER_USER = 40, 40 / 60     # ~40/min, burst 40
CAPACITY_PER_IP, RATE_PER_IP = 100, 100 / 60        # ~100/min, burst 100

DEFAULT_PER_USER = Limiter(capacity=CAPACITY_PER_USER, per_second=RATE_PER_USER)
DEFAULT_PER_IP = Limiter(capacity=CAPACITY_PER_IP, per_second=RATE_PER_IP)

# Health checks and docs are infrastructure, not user traffic.
EXEMPT_PREFIXES = ("/health", "/docs", "/openapi.json", "/redoc")


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _user_id(request: Request) -> str | None:
    """Best-effort identity from a bearer token, without a DB round trip.

    A middleware runs before route dependencies, so `get_current_user` has not
    resolved yet. An invalid or absent token just means the request is bucketed
    by IP only here — the route's own auth dependency still rejects it on its
    own merits afterward.
    """
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    token = header[7:].strip()
    if not token:
        return None
    try:
        payload = verify_token(token, token_type="access")
    except Exception:
        return None
    if not payload:
        return None
    user_id = payload.get("user_id") or payload.get("sub")
    return str(user_id) if user_id else None


async def _check(limiter: Limiter | RedisLimiter, key: str, now: float) -> None:
    """Duck-typed: `Limiter.check` is sync, `RedisLimiter.check` is a
    coroutine (a real network call is behind it). Awaiting only when there is
    something to await lets one middleware serve both without a branch at
    every call site."""
    result = limiter.check(key, now)
    if inspect.isawaitable(result):
        await result


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-user AND per-IP token buckets, both enforced — PRD-003.

    A per-user limit alone is evaded by registering more accounts; a per-IP
    limit alone is evaded from a phone. A request missing one key (no token,
    or the ASGI server did not set `request.client`) is still bounded by
    whichever key it does have — a missing key must never bucket everyone
    together, which a naive `key or "shared"` fallback would do.

    Prefers a Redis-backed store (distributed, correct under >1 instance) and
    falls back to the in-process one if Redis cannot be reached — the client
    is probed lazily on first request, not at construction, because
    `add_middleware` runs before the app's lifespan brings Redis up.
    """

    def __init__(
        self, app, *,
        per_user: Limiter = DEFAULT_PER_USER,
        per_ip: Limiter = DEFAULT_PER_IP,
        prefer_redis: bool = True,
    ) -> None:
        super().__init__(app)
        self._fallback = {"user": per_user, "ip": per_ip}
        self._prefer_redis = prefer_redis
        self._redis_limiters: dict[str, RedisLimiter] | None = None
        self._redis_unavailable = False

    async def _limiters(self) -> dict[str, Limiter | RedisLimiter]:
        if not self._prefer_redis or self._redis_unavailable:
            return self._fallback
        if self._redis_limiters is not None:
            return self._redis_limiters
        try:
            from backend.db.redis_client import get_redis
            client = await get_redis()
            self._redis_limiters = {
                "user": RedisLimiter(CAPACITY_PER_USER, RATE_PER_USER, client, prefix="rl:user"),
                "ip": RedisLimiter(CAPACITY_PER_IP, RATE_PER_IP, client, prefix="rl:ip"),
            }
            return self._redis_limiters
        except Exception:
            logger.warning(
                "rate limiter could not reach Redis; falling back to per-process "
                "limiting for this instance", exc_info=True,
            )
            self._redis_unavailable = True
            return self._fallback

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path.startswith(EXEMPT_PREFIXES):
            return await call_next(request)

        try:
            limiters = await self._limiters()
            keys = {"user": _user_id(request), "ip": _client_ip(request)}
            now = time.monotonic() if limiters is self._fallback else time.time()
            for name, limiter in limiters.items():
                key = keys.get(name)
                if key:
                    await _check(limiter, key, now)
        except RateLimited as exc:
            retry_after = int(exc.retry_after_seconds) + 1
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down."},
                headers={"Retry-After": str(retry_after)},
            )
        except Exception:
            # Fail OPEN: a limiter bug must degrade the protection, not the
            # service.
            logger.exception("rate limiter failed; allowing the request through")

        return await call_next(request)


__all__ = ["RateLimitMiddleware", "DEFAULT_PER_IP", "DEFAULT_PER_USER"]
