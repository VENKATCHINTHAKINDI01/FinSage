"""Buying property — PRC-007."""

from __future__ import annotations

from datetime import date

import pytest

from backend.core.costing.landed_cost import _load
from backend.core.provenance.money import Money
from backend.core.provenance.sourcing import SourcedFact, Tier
from backend.procurement.packs.property import (
    PropertyPurchase,
    StampDutyNotAvailable,
    build_pack,
    circle_rate_exposure,
    stamp_duty_line,
)

CFG = _load("procurement.yaml")
BOUGHT = date(2026, 6, 1)


def buy(consideration: str, circle: str, **kw) -> PropertyPurchase:
    base = {
        "state": "MH",
        "consideration": Money(consideration),
        "stamp_duty_value": Money(circle),
        "purchase_date": BOUGHT,
    }
    base.update(kw)
    return PropertyPurchase(**base)


def rate_fact(key: str, value: str) -> SourcedFact:
    return SourcedFact(
        key=key, value=value, source_url="https://igrmaharashtra.gov.in/x",
        tier=Tier.OFFICIAL, fetched_on=BOUGHT, source_kind="stamp_duty",
    )


# ── two provisions, not one warning ─────────────────────────────────────────

def test_a_shortfall_inside_both_tolerances_triggers_neither():
    seller, buyer, _ = circle_rate_exposure(
        buy("10000000", "10500000"), CFG,      # 5% short
    )
    assert not seller.triggered
    assert not buyer.triggered
    assert seller.amount == Money(0)
    assert buyer.amount == Money(0)


def test_a_large_shortfall_taxes_both_parties_on_the_same_sale():
    """Not one trap with two names. Two provisions, both biting."""
    seller, buyer, _ = circle_rate_exposure(
        buy("10000000", "12000000"), CFG,      # 20% short
    )
    assert seller.triggered and buyer.triggered
    # The seller's gains are recomputed on the circle rate...
    assert seller.amount == Money("12000000")
    # ...and the buyer is taxed on the gap as other income.
    assert buyer.amount == Money("2000000")


def test_the_fifty_thousand_floor_makes_the_two_limbs_diverge():
    """The case a single combined warning gets wrong for one of its readers.

    On a ₹4,00,000 plot, 10% is ₹40,000 and the buyer's tolerance is the
    ₹50,000 floor. A ₹45,000 shortfall taxes the seller and not the buyer.
    """
    seller, buyer, _ = circle_rate_exposure(buy("400000", "445000"), CFG)
    assert seller.tolerance == Money("40000")
    assert buyer.tolerance == Money("50000")
    assert seller.triggered
    assert not buyer.triggered

    pack = build_pack(buy("400000", "445000"), cfg=CFG,
                      facts={"stamp_duty.MH": rate_fact("stamp_duty.MH", "0.06")})
    assert pack.only_one_side_triggered


def test_the_tolerance_is_ten_percent_not_the_five_on_the_2018_section_page():
    """The department's own s.50C page is a 2018 snapshot carrying 105%. The
    Finance Act 2020 raised it to 110%. Encoding the section page alone would
    warn on transactions that are perfectly safe."""
    seller, _, _ = circle_rate_exposure(buy("10000000", "10800000"), CFG)
    assert seller.tolerance == Money("1000000")   # 10%, not 5%
    assert not seller.triggered                   # 8% short — inside


def test_a_price_above_the_circle_rate_is_not_a_shortfall():
    seller, buyer, _ = circle_rate_exposure(buy("12000000", "10000000"), CFG)
    assert seller.shortfall == Money(0)
    assert not seller.triggered and not buyer.triggered


def test_each_side_explains_itself_in_the_taxpayers_terms():
    seller, buyer, _ = circle_rate_exposure(buy("10000000", "12000000"), CFG)
    assert "money that never reached them" in seller.detail
    assert "a gift they did not receive" in buyer.detail
    assert "50C" in seller.section
    assert "56(2)(x)" in buyer.section


def test_the_worksheet_replays():
    _, _, trace = circle_rate_exposure(buy("10000000", "12000000"), CFG)
    assert trace.verify() == []


# ── stamp duty is not a table ───────────────────────────────────────────────

def test_an_ungathered_state_raises_rather_than_averaging():
    """An averaged stamp duty is wrong for most buyers by a percentage of the
    largest purchase of their life."""
    with pytest.raises(StampDutyNotAvailable, match="no admitted stamp duty"):
        stamp_duty_line(buy("10000000", "10000000", state="TR"), {})


def test_a_missing_rate_becomes_a_named_gap_not_a_silent_omission():
    pack = build_pack(buy("10000000", "10000000", state="TR"), cfg=CFG)
    assert pack.lines == []
    assert any("stamp_duty.TR" in g for g in pack.gaps)


def test_the_rate_comes_from_an_admitted_fact():
    line = stamp_duty_line(
        buy("10000000", "11000000"),
        {"stamp_duty.MH": rate_fact("stamp_duty.MH", "0.06")},
    )
    assert line.amount == Money("660000")      # 6% of the circle rate
    assert line.fact.tier is Tier.OFFICIAL


def test_a_woman_buyer_gets_the_concessional_rate_where_one_is_held():
    line = stamp_duty_line(
        buy("10000000", "10000000", buyer_is_female=True),
        {
            "stamp_duty.MH": rate_fact("stamp_duty.MH", "0.06"),
            "stamp_duty.MH.female": rate_fact("stamp_duty.MH.female", "0.05"),
        },
    )
    assert line.amount == Money("500000")
    assert "women-buyer" in line.label


def test_a_woman_buyer_with_no_concessional_rate_is_told_so():
    """Falling back to the general rate silently overstates the cost for
    roughly half of buyers."""
    pack = build_pack(
        buy("10000000", "10000000", buyer_is_female=True), cfg=CFG,
        facts={"stamp_duty.MH": rate_fact("stamp_duty.MH", "0.06")},
    )
    assert any("may be higher than what you will actually pay" in n
               for n in pack.notes)


# ── RERA ────────────────────────────────────────────────────────────────────

def test_an_under_construction_purchase_with_no_rera_number_is_flagged():
    pack = build_pack(
        buy("10000000", "10000000", is_under_construction=True), cfg=CFG,
        facts={"stamp_duty.MH": rate_fact("stamp_duty.MH", "0.06")},
    )
    assert any("RERA" in g for g in pack.gaps)
    assert any("not proof of anything" in g for g in pack.gaps)


def test_a_recorded_rera_number_is_not_claimed_to_have_been_checked():
    pack = build_pack(
        buy("10000000", "10000000", is_under_construction=True,
            rera_number="P51700012345"), cfg=CFG,
        facts={"stamp_duty.MH": rate_fact("stamp_duty.MH", "0.06")},
    )
    assert any("has not checked it" in n for n in pack.notes)


# ── restraint ───────────────────────────────────────────────────────────────

def test_nothing_in_the_pack_expresses_a_view_on_the_market():
    """Whether a locality will appreciate, or whether this is a good time to
    buy, are market judgements. PRC-007 makes none."""
    pack = build_pack(
        buy("10000000", "12000000", is_under_construction=True,
            buyer_is_female=True), cfg=CFG,
    )
    blob = " ".join(
        [pack.seller_exposure.detail, pack.buyer_exposure.detail,
         *pack.gaps, *pack.notes]
    ).lower()
    for word in ("appreciate", "good time", "undervalued", "overvalued",
                 "invest", "growth area", "will rise", "worth buying",
                 "negotiate down", "walk away"):
        assert word not in blob, word


def test_serialises_with_both_sides_kept_apart():
    d = build_pack(buy("400000", "445000"), cfg=CFG).to_dict()
    assert d["seller"]["triggered"] is True
    assert d["buyer"]["triggered"] is False
    assert d["only_one_side_triggered"] is True
    assert d["worksheet"]
