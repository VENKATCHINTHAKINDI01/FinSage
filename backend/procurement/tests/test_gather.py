"""Cache at answer time, search on the sweep — PRC-011."""

from __future__ import annotations

import inspect
from datetime import date, timedelta
from decimal import Decimal

from backend.core.provenance.admission import CandidateFact
from backend.core.provenance.sourcing import SourceCache, SourcedFact, Tier
from backend.procurement.gather import Gathered, resolve, sweep

TODAY = date(2026, 8, 13)


def official(key: str, value: str, *, fetched: date = TODAY,
             kind: str = "gst") -> SourcedFact:
    return SourcedFact(
        key=key, value=value, source_url="https://cbic.gov.in/rates",
        tier=Tier.OFFICIAL, fetched_on=fetched, source_kind=kind,
    )


def listing(key: str, value: str) -> SourcedFact:
    return SourcedFact(
        key=key, value=value, source_url="https://marketplace.example/x",
        tier=Tier.AGGREGATOR, fetched_on=TODAY, source_kind="oem_price_list",
    )


def candidate(key: str, raw: str, url: str, *, kind: str = "rate",
              by: str = "html_table_cell") -> CandidateFact:
    return CandidateFact(
        key=key, raw_value=raw, value_kind=kind, extracted_by=by,
        source_url=url, fetched_on=TODAY, source_kind="gst",
    )


# ── the guarantee is in the signature ───────────────────────────────────────

def test_resolve_cannot_be_handed_a_search_function():
    """The load-bearing assertion of this module.

    If `resolve` ever grows a `search` parameter — even one defaulting to None
    — the network is one keyword argument away from the critical path of every
    answer, and it will get there. The same test guards `FreshnessCache` having
    no fetch method (AGT-012).
    """
    params = set(inspect.signature(resolve).parameters)
    assert "search" not in params
    assert not any("fetch" in p or "search" in p for p in params)


def test_resolve_makes_no_call_to_anything_injected():
    """Belt and braces: even the objects it IS handed are read, not called."""
    cache = SourceCache({"gst.ev": official("gst.ev", "0.05")})
    got = resolve(["gst.ev"], cache, today=TODAY)
    assert got.facts["gst.ev"].value == "0.05"


# ── answer time ─────────────────────────────────────────────────────────────

def test_a_missing_key_is_a_named_gap_not_a_guess():
    got = resolve(["road_tax.TR"], SourceCache(), today=TODAY)
    assert got.facts == {}
    assert not got.complete
    assert got.gaps[0].key == "road_tax.TR"
    assert "not been gathered" in got.gaps[0].reason
    assert got.gaps[0].what_would_fix_it


def test_a_stale_fact_still_serves_and_is_flagged():
    """A labelled 40-day-old GST rate beats an error page. The rate has almost
    certainly not moved, and the badge is what tells a user to check."""
    old = official("gst.ev", "0.05", fetched=TODAY - timedelta(days=40))
    got = resolve(["gst.ev"], SourceCache({"gst.ev": old}), today=TODAY)
    assert "gst.ev" in got.facts          # served
    assert got.stale == ["gst.ev"]        # and flagged
    assert got.refresh_due == ["gst.ev"]


def test_a_tier_3_fact_is_context_and_also_a_gap():
    """Both, not either. It is shown so the user sees what we saw; it is a gap
    so the total does not silently omit a line without saying why."""
    cache = SourceCache({"price.laptop": listing("price.laptop", "62000")})
    got = resolve(["price.laptop"], cache, today=TODAY)
    assert got.facts == {}
    assert "price.laptop" in got.context
    assert got.gaps[0].key == "price.laptop"
    assert "aggregator" in got.gaps[0].reason


def test_gathered_serialises_both_halves():
    cache = SourceCache({
        "gst.ev": official("gst.ev", "0.05"),
        "price.laptop": listing("price.laptop", "62000"),
    })
    d = resolve(["gst.ev", "price.laptop", "road_tax.TR"], cache,
                today=TODAY).to_dict(TODAY)
    assert set(d["facts"]) == {"gst.ev"}
    assert set(d["context"]) == {"price.laptop"}
    assert {g["key"] for g in d["gaps"]} == {"price.laptop", "road_tax.TR"}
    assert d["complete"] is False


# ── the sweep ───────────────────────────────────────────────────────────────

def test_the_sweep_admits_and_fills_the_cache():
    cache = SourceCache()
    calls: list[str] = []

    def search(key, query):
        calls.append(key)
        return [candidate(key, "5%", "https://cbic.gov.in/rates")]

    report = sweep({"gst.ev": "gst rate electric vehicle"}, cache, search,
                   today=TODAY)
    assert report.admitted == ["gst.ev"]
    assert report.healthy
    assert cache.get("gst.ev").tier is Tier.OFFICIAL
    assert calls == ["gst.ev"]

    # And the answer path now finds it without a network call.
    assert resolve(["gst.ev"], cache, today=TODAY).complete


def test_the_sweep_skips_what_is_not_due_yet():
    """One request per fact per TTL, not one per answer."""
    cache = SourceCache({"gst.ev": official("gst.ev", "0.05")})
    called = []
    report = sweep({"gst.ev": "q"}, cache,
                   lambda k, q: called.append(k) or [], today=TODAY)
    assert report.unchanged == ["gst.ev"]
    assert called == []


def test_force_re_reads_a_fresh_fact():
    """For the re-verification run after a Budget, where age is not the point."""
    cache = SourceCache({"gst.ev": official("gst.ev", "0.18")})
    report = sweep(
        {"gst.ev": "q"}, cache,
        lambda k, q: [candidate(k, "5%", "https://cbic.gov.in/rates")],
        today=TODAY, force=True,
    )
    assert report.admitted == ["gst.ev"]
    assert cache.get("gst.ev").value == Decimal("0.05")


def test_a_failed_admission_does_not_evict_a_good_cached_fact():
    """One bad fetch must not turn a working answer into a gap. The Tier-1
    figure from last week, with its date on it, is still the best available."""
    stale_but_good = official("gst.ev", "0.05",
                              fetched=TODAY - timedelta(days=60))
    cache = SourceCache({"gst.ev": stale_but_good})
    report = sweep({"gst.ev": "q"}, cache, lambda k, q: [], today=TODAY)
    assert report.rejected == ["gst.ev"]
    assert not report.healthy
    assert cache.get("gst.ev") is stale_but_good
    assert "reported as gaps rather than estimated" in report.summary()


def test_a_model_authored_result_never_reaches_the_cache():
    """The sweep is the network boundary, so it is also where a hallucinated
    figure would enter the system if the gate were not in front of it."""
    cache = SourceCache()
    report = sweep(
        {"gst.ev": "q"}, cache,
        lambda k, q: [candidate(k, "5%", "https://cbic.gov.in/rates",
                                by="llm_stated")],
        today=TODAY,
    )
    assert report.rejected == ["gst.ev"]
    assert cache.get("gst.ev") is None


def test_a_listing_does_not_overwrite_an_official_fact():
    """Otherwise a sweep that happened to find a marketplace page first would
    silently demote a costable line to context."""
    good = official("price.laptop", "62000",
                    fetched=TODAY - timedelta(days=400), kind="oem_price_list")
    cache = SourceCache({"price.laptop": good})
    report = sweep(
        {"price.laptop": "q"}, cache,
        lambda k, q: [candidate(k, "₹61,000", "https://marketplace.example/x",
                                kind="money")],
        today=TODAY,
    )
    assert report.context_only == ["price.laptop"]
    assert cache.get("price.laptop") is good


def test_sweep_report_names_what_could_not_be_admitted():
    cache = SourceCache()
    report = sweep({"stamp_duty.TR": "q"}, cache, lambda k, q: [], today=TODAY)
    assert "stamp_duty.TR" in report.summary()
    assert report.to_dict()["healthy"] is False


def test_an_empty_gather_is_complete():
    assert Gathered().complete
    assert resolve([], SourceCache(), today=TODAY).complete
