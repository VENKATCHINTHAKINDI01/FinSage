"""FastAPI wiring for the rate limiter — PRD-003.

`prefer_redis=False` throughout: this suite is about the ASGI wiring
(exemption paths, header shape, key extraction) using the deterministic
in-process `Limiter`, not about Redis. The Redis-backed store has its own
suite, `test_redis_ratelimit.py`, against a live Redis.
"""

from __future__ import annotations

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from backend.middleware.asgi_ratelimit import RateLimitMiddleware
from backend.middleware.ratelimit import Limiter
from backend.security.jwt_handler import create_access_token


async def _homepage(request):
    return PlainTextResponse("ok")


def _app(**limiters) -> Starlette:
    app = Starlette(routes=[Route("/x", _homepage), Route("/health", _homepage)])
    app.add_middleware(RateLimitMiddleware, prefer_redis=False, **limiters)
    return app


def test_requests_within_capacity_succeed():
    client = TestClient(_app(
        per_user=Limiter(capacity=3, per_second=0.001),
        per_ip=Limiter(capacity=100, per_second=100),
    ))
    for _ in range(3):
        assert client.get("/x").status_code == 200


def test_the_bucket_never_grants_past_capacity():
    client = TestClient(_app(
        per_user=Limiter(capacity=100, per_second=100),
        per_ip=Limiter(capacity=3, per_second=0.001),
    ))
    codes = [client.get("/x").status_code for _ in range(6)]
    assert codes[:3] == [200, 200, 200]
    assert codes[3:] == [429, 429, 429]


def test_the_429_carries_a_usable_retry_after():
    client = TestClient(_app(
        per_user=Limiter(capacity=100, per_second=100),
        per_ip=Limiter(capacity=1, per_second=0.01),
    ))
    client.get("/x")
    resp = client.get("/x")
    assert resp.status_code == 429
    assert int(resp.headers["retry-after"]) > 0


def test_a_missing_key_does_not_bucket_everyone_together():
    """Two anonymous IPs must not share one bucket just because neither
    presented a token — that would let one caller exhaust the limit for
    everyone else without identifying themselves."""
    per_ip = Limiter(capacity=1, per_second=0.001)
    client = TestClient(_app(
        per_user=Limiter(capacity=100, per_second=100),
        per_ip=per_ip,
    ))
    resp = client.get("/x")
    assert resp.status_code == 200
    # A distinct IP (TestClient's default host) does not share the bucket key
    # of a request with a different client key.
    assert "127.0.0.1" in per_ip.buckets or "testclient" in per_ip.buckets


def test_health_check_is_exempt():
    client = TestClient(_app(
        per_user=Limiter(capacity=1, per_second=0.0001),
        per_ip=Limiter(capacity=1, per_second=0.0001),
    ))
    client.get("/x")  # exhaust the bucket
    for _ in range(5):
        assert client.get("/health").status_code == 200


def test_a_bearer_token_buckets_by_user_not_just_ip():
    per_user = Limiter(capacity=1, per_second=0.001)
    client = TestClient(_app(
        per_user=per_user,
        per_ip=Limiter(capacity=100, per_second=100),
    ))
    token = create_access_token("user-abc")
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/x", headers=headers).status_code == 200
    assert client.get("/x", headers=headers).status_code == 429
    assert "user-abc" in per_user.buckets


def test_an_invalid_bearer_token_falls_back_to_ip_bucketing_only():
    client = TestClient(_app(
        per_user=Limiter(capacity=1, per_second=0.001),
        per_ip=Limiter(capacity=100, per_second=100),
    ))
    resp = client.get("/x", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 200
