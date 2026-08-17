"""Source tiering — PRC-002 (pure half; fetchers are in backend/procurement).

One claim carries this module: a Tier-3 source cannot produce a rupee figure,
and that is enforced by the TYPE, not by anyone remembering. The tests are
written so that relaxing the constructor fails immediately.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from backend.core.provenance.money import rupees
from backend.core.provenance.sourcing import (
    CanaryResult,
    CostLine,
    SourceCache,
    SourcedFact,
    Tier,
    Tier3CannotCost,
    UndatedFact,
    canary_verdict,
    next_refresh_due,
)

TODAY = date(2026, 8, 12)


def fact(tier=Tier.OFFICIAL, kind="gst", fetched=TODAY, key="gst.electric_vehicle"):
    return SourcedFact(
        key=key, value="0.05", source_url="https://www.cbic.gov.in/gst-rates",
        tier=tier, fetched_on=fetched, source_kind=kind,
    )


# ══ the invariant ═══════════════════════════════════════════════════════════

class TestTierThreeCannotCost:
    def test_a_cost_line_from_an_aggregator_raises(self) -> None:
        """Enforced at construction. A validation flag can be ignored; a
        constructor that refuses cannot."""
        with pytest.raises(Tier3CannotCost, match="must never produce a figure"):
            CostLine("Ex-showroom price", rupees(840_000), fact(tier=Tier.AGGREGATOR))

    def test_the_error_names_the_source_and_what_to_do(self) -> None:
        with pytest.raises(Tier3CannotCost) as e:
            CostLine("Ex-showroom", rupees(840_000), fact(tier=Tier.AGGREGATOR))
        assert "cbic.gov.in" in str(e.value)
        assert "Find an official or manufacturer source" in str(e.value)

    @pytest.mark.parametrize("tier", [Tier.OFFICIAL, Tier.OEM_OR_BANK])
    def test_official_and_manufacturer_sources_may_cost(self, tier) -> None:
        assert CostLine("GST", rupees(42_000), fact(tier=tier)).amount == rupees(42_000)

    def test_the_permission_is_a_property_of_the_tier_itself(self) -> None:
        """So a caller can check before building, rather than catching."""
        assert Tier.OFFICIAL.may_drive_a_cost_line
        assert Tier.OEM_OR_BANK.may_drive_a_cost_line
        assert not Tier.AGGREGATOR.may_drive_a_cost_line

    def test_tiers_order_by_authority(self) -> None:
        assert Tier.OFFICIAL < Tier.OEM_OR_BANK < Tier.AGGREGATOR

    def test_a_deduction_line_is_still_gated(self) -> None:
        """A subsidy sourced from a blog is as wrong as a price from one."""
        with pytest.raises(Tier3CannotCost):
            CostLine("Subsidy", rupees(10_000), fact(tier=Tier.AGGREGATOR),
                     is_deduction=True)


class TestNoUndatedFact:
    def test_a_fact_without_a_fetch_date_raises(self) -> None:
        with pytest.raises(UndatedFact, match="only true as of a date"):
            SourcedFact("gst.ev", "0.05", "https://cbic.gov.in", Tier.OFFICIAL, None)

    def test_every_fact_renders_an_as_of_date(self) -> None:
        assert fact().to_dict()["as_of"] == "as of 12 August 2026"


# ══ per-source freshness ════════════════════════════════════════════════════

class TestFreshness:
    def test_each_source_kind_ages_at_its_own_rate(self) -> None:
        """One global TTL would either hammer stable endpoints or serve
        hour-old gold prices as current."""
        assert fact(kind="gold_rate").ttl_days < Decimal(1)
        assert fact(kind="state_ev_policy").ttl_days == Decimal(7)
        assert fact(kind="gst").ttl_days == Decimal(30)
        assert fact(kind="circle_rate").ttl_days == Decimal(90)

    def test_an_unknown_kind_gets_the_conservative_default(self) -> None:
        assert fact(kind="something_new").ttl_days == Decimal(30)

    def test_gold_is_stale_within_a_day(self) -> None:
        assert fact(kind="gold_rate", fetched=date(2026, 8, 11)).is_stale(TODAY)

    def test_a_gst_rate_is_not(self) -> None:
        assert not fact(kind="gst", fetched=date(2026, 8, 1)).is_stale(TODAY)

    def test_but_becomes_so_past_its_window(self) -> None:
        assert fact(kind="gst", fetched=date(2026, 6, 1)).is_stale(TODAY)

    def test_the_next_refresh_is_computable(self) -> None:
        assert next_refresh_due(fact(kind="state_ev_policy")) == date(2026, 8, 19)


class TestBadges:
    def test_a_stale_fact_carries_an_age_badge(self) -> None:
        badge = fact(kind="gst", fetched=date(2026, 5, 1)).badge(TODAY)
        assert "days old" in badge and "not re-checked" in badge

    def test_a_tier_three_fact_is_badged_as_context_only(self) -> None:
        badge = fact(tier=Tier.AGGREGATOR).badge(TODAY)
        assert "unverified" in badge
        assert "not a cost" in badge

    def test_a_fresh_official_fact_needs_no_badge(self) -> None:
        assert fact().badge(TODAY) == ""

    def test_both_conditions_appear_together(self) -> None:
        badge = fact(tier=Tier.AGGREGATOR, kind="gst",
                     fetched=date(2026, 5, 1)).badge(TODAY)
        assert "unverified" in badge and "days old" in badge


# ══ the cache serves stale rather than breaking ═════════════════════════════

class TestCache:
    def test_a_stale_fact_is_still_served(self) -> None:
        """A user with a labelled 40-day-old rate is better served than a user
        with an error page."""
        cache = SourceCache()
        cache.put(fact(kind="gst", fetched=date(2026, 6, 1)))
        served = cache.get("gst.electric_vehicle")
        assert served is not None
        assert served.is_stale(TODAY)

    def test_stale_facts_can_be_listed_for_the_sweep(self) -> None:
        cache = SourceCache()
        cache.put(fact(kind="gst", fetched=date(2026, 8, 1), key="fresh"))
        cache.put(fact(kind="gst", fetched=date(2026, 1, 1), key="old"))
        assert [f.key for f in cache.stale(TODAY)] == ["old"]

    def test_requiring_a_missing_fact_raises_rather_than_defaulting(self) -> None:
        """A cost line built on an assumed rate is the failure this whole
        module exists to prevent."""
        with pytest.raises(KeyError, match="cannot be built from an assumption"):
            SourceCache().require("gst.electric_vehicle")

    def test_tier_three_facts_are_separable_for_the_ui(self) -> None:
        cache = SourceCache()
        cache.put(fact(key="official"))
        cache.put(fact(tier=Tier.AGGREGATOR, key="listing"))
        assert [f.key for f in cache.context_only()] == ["listing"]


# ══ the nightly canary ══════════════════════════════════════════════════════

class TestCanary:
    def test_all_healthy_reports_so(self) -> None:
        v = canary_verdict([CanaryResult("gst", "https://cbic.gov.in", True, TODAY)])
        assert v["healthy"] and not v["failed"]

    def test_a_failure_is_reported_without_claiming_breakage(self) -> None:
        """A dead fetcher does not break the product — the cache keeps serving.
        It does mean nobody will notice a rate change, which is the actual
        risk and what the message has to say."""
        v = canary_verdict([
            CanaryResult("gst", "https://cbic.gov.in", True, TODAY),
            CanaryResult("road_tax", "https://parivahan.gov.in", False, TODAY,
                         "timeout"),
        ])
        assert not v["healthy"]
        assert v["checked"] == 2 and len(v["failed"]) == 1
        assert "nothing is broken" in v["message"]
        assert "nobody will see a rate change" in v["message"]


def test_a_cost_line_serialises_with_its_source() -> None:
    line = CostLine("GST at 5%", rupees(42_000), fact())
    d = line.to_dict(TODAY)
    assert d["display"] == "₹42,000"
    assert d["source"]["tier"] == 1
    assert d["source"]["may_drive_a_cost_line"] is True


def test_a_deduction_signs_negative() -> None:
    line = CostLine("State EV subsidy", rupees(10_000), fact(), is_deduction=True)
    assert line.signed == rupees(-10_000)
