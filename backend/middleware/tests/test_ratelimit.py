"""Rate limits, spend caps and upload validation — PRD-003."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from backend.middleware.ratelimit import (
    Bucket,
    InMemorySpend,
    Limiter,
    RateLimited,
    SpendCapReached,
    UploadRejected,
    check_upload,
    guard,
    read_capped,
    reconcile,
    reserve,
    sniff,
)

TODAY = date(2026, 8, 13)


# ── token bucket, not a fixed window ────────────────────────────────────────

def test_a_fixed_window_burst_is_not_possible():
    """The property a fixed window fails.

    60/minute as a fixed window lets a caller send 60 at 11:59:59 and 60 more
    at 12:00:00 — 120 within a second. A bucket crossing the same boundary has
    refilled at the RATE, so it grants one more request, not another sixty.

    An earlier version of this test asserted the boundary request should fail
    outright. It should not: at one per second, one second later you are owed
    one token. The claim being made is about the SIZE of the burst, not about
    refusing at the boundary.
    """
    limiter = Limiter(capacity=60, per_second=1.0)
    for i in range(60):
        limiter.check("u-1", now=59.0 + i * 0.001)

    granted = 0
    for _ in range(60):
        try:
            limiter.check("u-1", now=60.0)
            granted += 1
        except RateLimited:
            break

    assert granted == 1, "a fixed window would have granted 60 here"


def test_the_bucket_refills_continuously():
    limiter = Limiter(capacity=2, per_second=1.0)
    limiter.check("u-1", now=0.0)
    limiter.check("u-1", now=0.0)
    with pytest.raises(RateLimited):
        limiter.check("u-1", now=0.0)

    limiter.check("u-1", now=1.0)           # one token back after one second


def test_it_never_refills_past_capacity():
    """Otherwise a caller idle for an hour arrives with 3,600 requests in
    hand, which is a burst with extra steps."""
    bucket = Bucket(capacity=5, per_second=1.0)
    bucket.take(now=0.0)
    for _ in range(5):
        bucket.take(now=10_000.0)
    with pytest.raises(RateLimited):
        bucket.take(now=10_000.0)


def test_the_wait_it_reports_is_actually_long_enough():
    """A retry-after that is too short turns a limit into a busy loop."""
    limiter = Limiter(capacity=1, per_second=0.5)
    limiter.check("u-1", now=0.0)
    with pytest.raises(RateLimited) as exc:
        limiter.check("u-1", now=0.0)

    limiter.check("u-1", now=exc.value.retry_after_seconds)


def test_keys_do_not_share_a_bucket():
    limiter = Limiter(capacity=1, per_second=0.0001)
    limiter.check("u-1", now=0.0)
    limiter.check("u-2", now=0.0)


def test_both_the_user_and_the_ip_limit_are_applied():
    """A per-user limit alone is evaded by making accounts; a per-IP limit
    alone is evaded from a phone."""
    limiters = {
        "user": Limiter(capacity=10, per_second=1.0),
        "ip": Limiter(capacity=1, per_second=0.001),
    }
    guard(limiters, {"user": "u-1", "ip": "1.2.3.4"}, now=0.0)
    with pytest.raises(RateLimited):
        guard(limiters, {"user": "u-2", "ip": "1.2.3.4"}, now=0.0)


def test_a_missing_key_skips_that_limiter_rather_than_bucketing_everyone_together():
    """An empty key would put every anonymous caller in one bucket, so the
    first of them consumes the limit for all the rest."""
    limiters = {"user": Limiter(capacity=1, per_second=0.001)}
    guard(limiters, {"user": ""}, now=0.0)
    guard(limiters, {"user": ""}, now=0.0)


# ── spend cap: reserve before, reconcile after ──────────────────────────────

def test_the_estimate_is_taken_before_the_call():
    """Checking the bill afterwards is checking whether the money is already
    gone."""
    store = InMemorySpend()
    reserve("u-1", store, estimate=Decimal("2.00"), cap=Decimal("10.00"), on=TODAY)
    assert store.spent_today("u-1", TODAY) == Decimal("2.00")


def test_a_call_that_would_breach_the_cap_is_refused():
    store = InMemorySpend()
    reserve("u-1", store, estimate=Decimal("9.00"), cap=Decimal("10.00"), on=TODAY)
    with pytest.raises(SpendCapReached, match="resets tomorrow"):
        reserve("u-1", store, estimate=Decimal("2.00"), cap=Decimal("10.00"), on=TODAY)


def test_reconciliation_refunds_an_overestimate():
    store = InMemorySpend()
    r = reserve("u-1", store, estimate=Decimal("5.00"), cap=Decimal("10.00"), on=TODAY)
    reconcile(r, store, actual=Decimal("1.25"))
    assert store.spent_today("u-1", TODAY) == Decimal("1.25")


def test_an_underestimate_overshoots_by_at_most_one_call():
    """Bounded and worth stating. The alternative is not reserving at all,
    which is unbounded."""
    store = InMemorySpend()
    r = reserve("u-1", store, estimate=Decimal("1.00"), cap=Decimal("10.00"), on=TODAY)
    reconcile(r, store, actual=Decimal("40.00"))
    assert store.spent_today("u-1", TODAY) == Decimal("40.00")

    with pytest.raises(SpendCapReached):
        reserve("u-1", store, estimate=Decimal("0.01"), cap=Decimal("10.00"), on=TODAY)


def test_the_cap_is_per_user():
    store = InMemorySpend()
    reserve("u-1", store, estimate=Decimal("9.99"), cap=Decimal("10.00"), on=TODAY)
    reserve("u-2", store, estimate=Decimal("9.99"), cap=Decimal("10.00"), on=TODAY)


def test_the_cap_resets_the_next_day():
    store = InMemorySpend()
    reserve("u-1", store, estimate=Decimal("10.00"), cap=Decimal("10.00"), on=TODAY)
    reserve("u-1", store, estimate=Decimal("10.00"), cap=Decimal("10.00"),
            on=date(2026, 8, 14))


# ── the opposite failure modes ──────────────────────────────────────────────

def test_the_spend_cap_fails_closed():
    """An unavailable counter means we do not know what has been spent, and
    'unknown' is not a number you can be under. A store outage must not become
    an unbounded bill."""
    store = InMemorySpend(available=False)
    with pytest.raises(SpendCapReached, match="unavailable"):
        reserve("u-1", store, estimate=Decimal("0.01"), cap=Decimal("100.00"),
                on=TODAY)


def test_the_rate_limiter_fails_open():
    """The opposite decision, on purpose. Taking the service down because the
    limiter is down converts a degradation into an outage and does the
    attacker's job."""
    limiters = {"user": Limiter(capacity=1, per_second=0.001)}
    guard(limiters, {}, now=0.0)            # no key resolvable — allowed
    guard(limiters, {}, now=0.0)


# ── uploads: an extension is not a type ─────────────────────────────────────

def test_a_pdf_is_recognised_by_its_first_bytes():
    assert check_upload(b"%PDF-1.7\n%\xe2\xe3") == "application/pdf"


def test_a_zip_renamed_to_pdf_is_refused():
    """A file named invoice.pdf that starts with PK is a zip, and a zip handed
    to a PDF parser is at best an error and at worst an unpacking bomb."""
    with pytest.raises(UploadRejected, match="recognised signature"):
        check_upload(b"PK\x03\x04payload")


def test_a_real_png_is_refused_where_only_pdf_is_accepted():
    with pytest.raises(UploadRejected, match="image/png"):
        check_upload(b"\x89PNG\r\n\x1a\nrest")


def test_a_declared_type_that_disagrees_with_the_contents_is_refused():
    """A mismatch is worth refusing on its own — it is either a mistake or an
    attempt."""
    with pytest.raises(UploadRejected, match="claims to be"):
        check_upload(b"%PDF-1.7", declared_type="image/png")


def test_the_sniffed_type_is_returned_never_the_declared_one():
    """So a caller using the return value cannot accidentally trust the
    uploader's word."""
    assert check_upload(b"%PDF-1.7", declared_type="application/pdf") == "application/pdf"
    assert sniff(b"%PDF-") == "application/pdf"
    assert sniff(b"not a known header") is None


def test_an_empty_upload_is_refused():
    with pytest.raises(UploadRejected):
        check_upload(b"")


def test_an_oversized_upload_is_refused_during_the_read():
    """Reading a 4 GB upload into memory to discover it is too large IS the
    attack. The refusal has to happen before the bytes are all resident."""
    consumed = []

    def chunks():
        for i in range(1000):
            consumed.append(i)
            yield b"x" * 1024

    with pytest.raises(UploadRejected, match="exceeds"):
        read_capped(chunks(), limit=4096)

    assert len(consumed) < 10          # stopped early, did not drain the stream


def test_an_upload_inside_the_limit_is_returned_whole():
    data = read_capped([b"%PDF-", b"rest"], limit=4096)
    assert data == b"%PDF-rest"


def test_a_refusal_does_not_echo_the_file_back():
    """An error that quotes the payload is a reflection gadget."""
    payload = b"PK\x03\x04<script>alert(1)</script>"
    with pytest.raises(UploadRejected) as exc:
        check_upload(payload)
    assert "script" not in str(exc.value)
