# Load and resilience — PRD-007

## Status: partially measured (2026-08-17), not via k6

`chat.js` and `compute.js` were referenced here as "checked in" but were never
actually written — there was no k6 scenario file in this directory, only this
description of one. No k6 binary is available in this environment either.
What follows instead is a real, one-off load test run directly against the
live stack (uvicorn, single worker, real Postgres/Redis/Qdrant via
docker-compose) using a small asyncio/httpx script, not a permanent CI
fixture. It found and led to fixing a real bug; the numbers below are
measured, not projected.

## What was actually measured

**`/health` (rate-limit exempt, no DB): 20 concurrent workers, 300 requests.**
p50 17ms, p95 26–29ms, p99 33ms, 0 non-2xx. This is close to the floor for
this stack — routing plus middleware overhead with no real work behind it.

**`POST /api/v1/auth/register` (real Postgres writes + bcrypt): 20 concurrent
workers, 80 requests, sized to stay under the per-IP rate-limit budget.**

- *Before* fix: **p95 = 4639ms**, p50 = 4385ms. `hash_password()` (passlib
  bcrypt) was called synchronously inside the async route handler. Bcrypt is
  deliberately slow — that's the point of a password hash — and being
  synchronous CPU-bound work, it blocked the single-threaded event loop for
  its full duration on every call. Twenty concurrent registrations serialized
  almost completely onto one core: ~20 × 220ms ≈ the observed 4.4s.
- *After* wrapping both `hash_password` and `verify_password` call sites in
  `asyncio.to_thread` (`backend/api/auth.py`): **p95 = 1236ms**, p50 = 783ms.
  Throughput went from 4.5 req/s to 24.5 req/s — a 5.4x improvement from a
  two-line fix, because the bug was never in bcrypt's cost, it was in bcrypt
  running where nothing else could run at the same time.

This also means every authenticated request through this process was
degraded during any concurrent registration or login before the fix — not
just the registration endpoint itself, since a blocked event loop blocks
everyone sharing it.

**Rate limiter under sustained single-IP load**: confirmed to engage
correctly (429s with a usable `Retry-After`) once the per-IP bucket (capacity
100) is exhausted, both against the in-process `Limiter` and the Redis-backed
`RedisLimiter` — see `backend/middleware/asgi_ratelimit.py` and
`redis_ratelimit.py`. A single load-generating IP hitting several endpoints
in sequence shares one bucket, which is correct behaviour, not a test bug,
but it means a from-one-machine load test cannot cleanly separate "endpoint
p95" from "rate limiter p95" without pacing requests to stay under the
budget — which is what the register numbers above do.

## What is still NOT measured

- The actual "expensive path" (an LLM-involved chat/agent request) — needs a
  `GROQ_API_KEY` and budget for live calls; tracked together with AGT-005's
  live eval mode, not duplicated here.
- Groq/Redis/Qdrant outages have not been induced and observed (`chaos.md`'s
  matrix remains asserted, not exercised).
- Multi-instance / horizontal-scaling behavior (the Redis-backed rate limiter
  is built and unit-tested for this, but no second app instance was actually
  run against the same Redis to confirm the shared bucket behaves as one).
- No sustained-duration run (this was request-count bounded, not a
  time-boxed soak test) — nothing here rules out a slow leak.

## Scenarios

- `chaos.md` — the outage matrix and what each should degrade to. Still
  unexercised; see above.
