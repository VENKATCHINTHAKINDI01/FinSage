"""Rate limits, spend caps and upload validation — PRD-003.

Three different problems that get lumped together, and they want opposite
answers when things go wrong.

Rate limiting: fail OPEN
-------------------------
If the counter store is unreachable, allow the request. A rate limiter exists
to protect the service from load; taking the service down because the limiter
is down converts a degradation into an outage, and does the attacker's job.

Spend caps: fail CLOSED
------------------------
If the spend counter is unreachable, REFUSE. The cap exists to bound money. An
unavailable counter means we do not know how much has been spent today, and
"unknown" is not a number you can be under. This is the opposite of the
decision above, on purpose, and getting it backwards is how a store outage
becomes an unbounded bill.

Why a token bucket rather than a fixed window
----------------------------------------------
A fixed window of 60/minute lets a caller send 60 at 11:59:59 and 60 more at
12:00:00 — 120 in a second, which is exactly the burst the limit was written to
prevent. A bucket refills continuously, so the stated rate is the actual rate
and burst is a separate, explicit parameter.

Reserve before, reconcile after
--------------------------------
The obvious spend cap checks the bill after the call, by which time the money
is gone. But the cost is not known until the call returns. So a call RESERVES
an estimate first — refused if the estimate would breach the cap — and
reconciles the true cost afterwards. An underestimate can still overshoot by
one call's worth, which is bounded and stated, rather than by a whole runaway
loop.

Uploads: an extension is not a type
------------------------------------
`.pdf` is a claim by the uploader. The magic bytes are evidence. And size is
checked while STREAMING, because reading the file to measure it is the attack.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Protocol


class RateLimited(Exception):
    """429. Carries the wait so the client can back off usefully."""

    def __init__(self, retry_after_seconds: float, detail: str = "") -> None:
        super().__init__(detail or "rate limited")
        self.retry_after_seconds = max(0.0, retry_after_seconds)
        self.detail = detail


class SpendCapReached(Exception):
    """402/429. The user has used their budget for the day."""


class UploadRejected(Exception):
    """400. Names what was wrong without echoing the file back."""


# ── token bucket ────────────────────────────────────────────────────────────

@dataclass(slots=True)
class Bucket:
    """Continuous refill. `capacity` is the burst, `per_second` is the rate."""

    capacity: float
    per_second: float
    tokens: float = 0.0
    # `None`, not 0.0. An in-band sentinel means a bucket first used at
    # timestamp zero is treated as never used, refills to full on its second
    # call, and hands out an extra burst. Found by a test that legitimately
    # started the clock at zero.
    updated_at: float | None = None

    def _refill(self, now: float) -> None:
        if self.updated_at is None:
            self.tokens = self.capacity
            self.updated_at = now
            return
        elapsed = max(0.0, now - self.updated_at)
        self.tokens = min(self.capacity, self.tokens + elapsed * self.per_second)
        self.updated_at = now

    def take(self, now: float, cost: float = 1.0) -> None:
        self._refill(now)
        if self.tokens < cost:
            deficit = cost - self.tokens
            raise RateLimited(
                deficit / self.per_second if self.per_second else 3600.0,
                f"bucket empty: {self.tokens:.2f} of {cost} tokens available.",
            )
        self.tokens -= cost


@dataclass(slots=True)
class Limiter:
    """Per-key buckets. The key is whatever the caller decides to bound —
    a user id, an IP, or both, because either alone is trivially evaded."""

    capacity: float
    per_second: float
    buckets: dict[str, Bucket] = field(default_factory=dict)

    def check(self, key: str, now: float, cost: float = 1.0) -> None:
        bucket = self.buckets.get(key)
        if bucket is None:
            bucket = Bucket(self.capacity, self.per_second)
            self.buckets[key] = bucket
        bucket.take(now, cost)


def guard(limiters: dict[str, Limiter], keys: dict[str, str], now: float) -> None:
    """Every applicable limit, not just the first that matches.

    A per-user limit alone is evaded by making accounts; a per-IP limit alone
    is evaded from a phone. Both, and the tightest one wins by being checked.
    """
    for name, limiter in limiters.items():
        key = keys.get(name)
        if key:
            limiter.check(key, now)


# ── spend cap ───────────────────────────────────────────────────────────────

class SpendStore(Protocol):
    """Today's spend per user. Raises if it cannot answer."""

    def spent_today(self, user_id: str, on: date) -> Decimal: ...
    def add(self, user_id: str, on: date, amount: Decimal) -> None: ...


@dataclass(slots=True)
class InMemorySpend:
    """Reference implementation, and what the tests define the semantics by."""

    ledger: dict[tuple[str, str], Decimal] = field(default_factory=dict)
    available: bool = True

    def _guard(self) -> None:
        if not self.available:
            raise ConnectionError("spend store unavailable")

    def spent_today(self, user_id: str, on: date) -> Decimal:
        self._guard()
        return self.ledger.get((user_id, on.isoformat()), Decimal(0))

    def add(self, user_id: str, on: date, amount: Decimal) -> None:
        self._guard()
        key = (user_id, on.isoformat())
        self.ledger[key] = self.ledger.get(key, Decimal(0)) + amount


@dataclass(frozen=True, slots=True)
class Reservation:
    user_id: str
    on: date
    estimate: Decimal


def reserve(
    user_id: str, store: SpendStore, *, estimate: Decimal, cap: Decimal,
    on: date,
) -> Reservation:
    """Take the estimate BEFORE the call, or refuse.

    Checking the bill afterwards is checking whether the money is already gone.
    Fails CLOSED: if the store cannot say what has been spent, the cap cannot
    be enforced, and an unenforceable cap is not a cap.
    """
    try:
        already = store.spent_today(user_id, on)
    except Exception as exc:
        raise SpendCapReached(
            "the spend counter is unavailable, so today's usage cannot be "
            "checked. Refusing rather than proceeding — an uncheckable cap is "
            "not a cap, and a store outage must not become an unbounded bill."
        ) from exc

    if already + estimate > cap:
        raise SpendCapReached(
            f"today's LLM budget is {cap} and {already} has been used; this "
            f"call is estimated at {estimate}. It resets tomorrow."
        )

    store.add(user_id, on, estimate)
    return Reservation(user_id=user_id, on=on, estimate=estimate)


def reconcile(reservation: Reservation, store: SpendStore, *, actual: Decimal) -> None:
    """Correct the reservation once the true cost is known.

    A negative delta refunds an overestimate. An underestimate can overshoot
    the cap by at most one call's difference, which is bounded and worth
    stating plainly — the alternative is not reserving at all, which is
    unbounded.
    """
    store.add(reservation.user_id, reservation.on, actual - reservation.estimate)


# ── uploads ─────────────────────────────────────────────────────────────────

# Magic bytes, because an extension is a claim by the uploader and these are
# evidence. A file named invoice.pdf that starts with "PK" is a zip, and a zip
# handed to a PDF parser is at best an error and at worst an unpacking bomb.
SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "application/pdf": (b"%PDF-",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
}

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def sniff(head: bytes) -> str | None:
    for media_type, magics in SIGNATURES.items():
        if any(head.startswith(magic) for magic in magics):
            return media_type
    return None


def check_upload(
    head: bytes,
    *,
    declared_type: str = "",
    allowed: tuple[str, ...] = ("application/pdf",),
) -> str:
    """The real media type, or a refusal.

    Returns the SNIFFED type, never the declared one, so a caller that uses the
    return value cannot accidentally trust the uploader's word.
    """
    actual = sniff(head)
    if actual is None:
        raise UploadRejected(
            "the file does not begin with a recognised signature. An extension "
            "is a claim by whoever uploaded it; the first bytes are evidence, "
            "and these match nothing we accept."
        )
    if actual not in allowed:
        raise UploadRejected(
            f"this is a {actual} file. Only {', '.join(allowed)} is accepted "
            f"here."
        )
    if declared_type and declared_type != actual:
        raise UploadRejected(
            f"the upload claims to be {declared_type} but its contents are "
            f"{actual}. A mismatch is worth refusing on its own — it is either "
            f"a mistake or an attempt."
        )
    return actual


def read_capped(chunks: Any, *, limit: int = MAX_UPLOAD_BYTES) -> bytes:
    """Read a stream, refusing once the limit is passed.

    Refuses DURING the read, not after. Reading a 4 GB upload into memory to
    discover it is too large IS the attack — the check has to happen before the
    bytes are all resident.
    """
    out = bytearray()
    for chunk in chunks:
        out.extend(chunk)
        if len(out) > limit:
            raise UploadRejected(
                f"the upload exceeds {limit // (1024 * 1024)} MB. It was "
                f"refused part-way through rather than after being read into "
                f"memory."
            )
    return bytes(out)


__all__ = [
    "MAX_UPLOAD_BYTES",
    "SIGNATURES",
    "Bucket",
    "InMemorySpend",
    "Limiter",
    "RateLimited",
    "Reservation",
    "SpendCapReached",
    "SpendStore",
    "UploadRejected",
    "check_upload",
    "guard",
    "read_capped",
    "reconcile",
    "reserve",
    "sniff",
]
