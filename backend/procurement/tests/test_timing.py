"""Dated signals, and the forecast that must not appear — PRC-005."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from backend.core.costing.landed_cost import Purchase, _load
from backend.core.eligibility import Facts
from backend.core.provenance.money import Money
from backend.procurement.timing import (
    Kind,
    Ledger,
    Signal,
    build_ledger,
    depreciation_boundary,
    rate_changes,
    scheme_cliffs,
)

CFG = _load("procurement.yaml")
GST = _load("gst.yaml")
TODAY = date(2026, 8, 13)


def business_van(**kw):
    base = {
        "item": "Delivery van",
        "ex_showroom": Money("1200000"),
        "category": "commercial_vehicle",
        "state": "KA",
        "purchase_date": TODAY,
        "is_business_use": True,
        "is_gst_registered": True,
        "business_use_kind": "goods_transport",
        "depreciation_block": "motor_vehicle_commercial_hire",
        "marginal_tax_rate": Decimal("0.30"),
    }
    base.update(kw)
    return Purchase(**base)


# ── the refusal, enforced structurally ──────────────────────────────────────

def test_an_observed_pattern_cannot_carry_a_rupee_impact():
    """Attaching one turns "this happened in 2021-24" into "this will be worth
    ₹X to you", which is a forecast wearing a fact's clothes."""
    with pytest.raises(ValueError, match="must not carry a rupee impact"):
        Signal(
            kind=Kind.OBSERVED_PATTERN,
            label="Model-year clearance",
            on=None,
            detail="",
            impact=Money("40000"),
            years_observed=(2021, 2022),
        )


def test_an_observed_pattern_must_say_which_years():
    """Without them it reads as a general truth about how the market
    behaves."""
    with pytest.raises(ValueError, match="must state the years"):
        Signal(kind=Kind.OBSERVED_PATTERN, label="Festive discounts",
               on=None, detail="")


def test_a_dated_signal_must_carry_its_date():
    with pytest.raises(ValueError, match="must carry the date"):
        Signal(kind=Kind.POLICY_CLIFF, label="Something closes", on=None,
               detail="")


def test_a_pattern_can_never_reach_the_quantified_total():
    """By construction, not by filtering — the impact field is refused at
    construction, so there is nothing to leak into the sum."""
    ledger = Ledger(signals=[
        Signal(Kind.OBSERVED_PATTERN, "Model-year clearance", None,
               "Outgoing stock was discounted.", years_observed=(2021, 2024)),
        Signal(Kind.POLICY_CLIFF, "A scheme closes", date(2027, 3, 31),
               "", impact=Money("78000")),
    ], today=TODAY)
    assert ledger.quantified == Money("78000")


def test_a_pattern_sentence_says_it_is_a_record_not_a_statement():
    s = Signal(Kind.OBSERVED_PATTERN, "Model-year clearance", None,
               "Dealers cleared outgoing stock.", years_observed=(2021, 2022, 2023))
    said = s.sentence(TODAY)
    assert "observed in 2021, 2022, 2023" in said
    assert "not a statement about what will" in said


FORECAST_WORDS = [
    r"\bwill (?:fall|rise|drop|increase|decrease|be cheaper|go up|go down)\b",
    r"\bexpect(?:ed|ing)?\b", r"\blikely\b", r"\bpredict\w*\b",
    r"\bforecast\w*\b", r"\banticipat\w*\b", r"\bprojected\b",
    r"\bshould (?:fall|drop|rise|come down)\b", r"\btrend(?:ing)? (?:up|down)\b",
    r"\bbest time to buy\b", r"\bwait (?:for|until)\b",
]


def test_no_rendered_signal_contains_predictive_language():
    """The eval this feature exists to pass. Applied to every sentence the
    module can actually produce, not to a sample."""
    ledger = build_ledger(
        today=TODAY,
        facts=Facts(values={
            "asset_type": "rooftop_solar", "connection_type": "residential",
            "installation_mode": "capex", "domestic_content_modules": True,
            "capacity_kw": "3", "purchase_date": TODAY,
        }, as_of=TODAY),
        purchase=business_van(),
        fy="2026-27",
        cfg=CFG,
        gst_pack=GST,
        patterns=[
            Signal(Kind.OBSERVED_PATTERN, "Model-year clearance", None,
                   "Dealers discounted outgoing stock.",
                   years_observed=(2021, 2022, 2023, 2024)),
        ],
    )
    blob = " ".join(
        s.sentence(TODAY) for s in
        ledger.upcoming + ledger.passed + ledger.patterns
    ).lower()
    assert blob
    for pattern in FORECAST_WORDS:
        assert not re.search(pattern, blob), f"{pattern} found in: {blob}"


def test_the_ledger_declares_that_it_contains_no_forecasts():
    d = Ledger(signals=[], today=TODAY).to_dict()
    assert d["contains_forecasts"] is False


# ── the 31 March boundary, computed both ways ───────────────────────────────

def test_the_year_end_boundary_is_recomputed_not_asserted():
    """The one piece of timing advice here that is arithmetic rather than
    judgement. Both sides go through the costing model."""
    signal = depreciation_boundary(business_van(), "2026-27", today=TODAY,
                                   cfg=CFG)
    assert signal is not None
    assert signal.kind is Kind.TAX_BOUNDARY
    assert signal.on == date(2027, 3, 31)
    assert signal.impact > Money(0)


def test_the_boundary_explains_that_the_other_half_is_not_lost():
    """Otherwise it reads as "buy by March or lose the money", which is false
    and is exactly the manufactured urgency this module refuses."""
    signal = depreciation_boundary(business_van(), "2026-27", today=TODAY,
                                   cfg=CFG)
    assert "is not lost" in signal.detail
    assert "WHEN the deduction lands, not whether" in signal.detail
    assert "180 days" in signal.detail


def test_no_boundary_signal_for_a_buyer_it_cannot_affect():
    """A salaried person buying a car for the school run has no depreciation.
    Telling them to hurry before 31 March would be fabricated urgency."""
    personal = business_van(is_business_use=False, depreciation_block="",
                            is_gst_registered=False, business_use_kind="")
    assert depreciation_boundary(personal, "2026-27", today=TODAY,
                                 cfg=CFG) is None


def test_no_boundary_signal_once_the_year_end_has_passed():
    assert depreciation_boundary(business_van(), "2026-27",
                                 today=date(2027, 5, 1), cfg=CFG) is None


# ── scheme cliffs come from the eligibility engine ──────────────────────────

def test_a_live_scheme_produces_a_dated_cliff_with_its_value():
    facts = Facts(values={
        "asset_type": "rooftop_solar", "connection_type": "residential",
        "installation_mode": "capex", "domestic_content_modules": True,
        "capacity_kw": "3", "purchase_date": TODAY,
    }, as_of=TODAY)
    cliffs = scheme_cliffs(facts, today=TODAY)
    surya = [s for s in cliffs if "Surya Ghar" in s.label and "closes" in s.label]
    assert surya
    assert surya[0].on == date(2027, 3, 31)
    assert surya[0].impact == Money("78000")
    assert "not a market guess" in surya[0].detail


def test_a_closed_scheme_is_recorded_as_passed_with_its_reason():
    facts = Facts(values={
        "asset_type": "electric_vehicle", "taxpayer_type": "individual",
        "loan_sanction_date": date(2024, 5, 1), "purchase_date": TODAY,
    }, as_of=TODAY, regime="old")
    ledger = build_ledger(today=TODAY, facts=facts)
    closed = [s for s in ledger.passed if "80EEB" in s.label or "electric vehicle loan" in s.label]
    assert closed
    assert closed[0].on == date(2023, 3, 31)


def test_a_closed_cliff_carries_no_impact():
    """A benefit you cannot have is not worth anything to you, and putting its
    statutory ceiling in the quantified total would inflate the number the
    ledger reports."""
    facts = Facts(values={
        "asset_type": "electric_vehicle", "taxpayer_type": "individual",
        "loan_sanction_date": date(2024, 5, 1), "purchase_date": TODAY,
    }, as_of=TODAY, regime="old")
    for s in scheme_cliffs(facts, today=TODAY):
        if "closed" in s.label:
            assert s.impact is None


def test_the_cliff_dates_come_from_the_rule_pack_not_a_second_list():
    """No scheme date is hardcoded in this module.

    Restating them here would give the product two sources of truth about when
    80EEB shut, and the one nobody looks at would rot. Checked over the AST
    rather than the file text, so the prose in the docstrings — which does
    name 80EEB, deliberately, to explain the distinction — does not trip it.
    """
    import ast

    import backend.procurement.timing as timing

    tree = ast.parse(Path(timing.__file__).read_text(encoding="utf-8"))
    docstrings = {
        ast.get_docstring(n, clean=False)
        for n in ast.walk(tree)
        if isinstance(n, ast.Module | ast.ClassDef | ast.FunctionDef)
    }
    iso = re.compile(r"\d{4}-\d{2}-\d{2}")
    offenders = [
        n.value for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
        and n.value not in docstrings and iso.search(n.value)
    ]
    assert offenders == [], offenders

    # And no date literal built by hand either.
    calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        and n.func.id == "date"
        and all(isinstance(a, ast.Constant) for a in n.args)
    ]
    assert calls == [], [ast.unparse(c) for c in calls]


# ── rate changes ────────────────────────────────────────────────────────────

def test_the_gst_abolition_date_is_a_signal():
    signals = rate_changes(GST, today=TODAY)
    assert signals
    assert any(s.on == date(2025, 9, 22) for s in signals)
    assert any("abolished" in s.detail for s in signals)


def test_an_abolished_slab_is_described_as_out_of_date_not_as_a_view():
    signals = rate_changes(GST, today=TODAY)
    assert any("not a different opinion" in s.detail for s in signals)


# ── ordering and rendering ──────────────────────────────────────────────────

def test_upcoming_is_nearest_first_and_passed_is_most_recent_first():
    ledger = Ledger(signals=[
        Signal(Kind.POLICY_CLIFF, "Far", date(2028, 1, 1), ""),
        Signal(Kind.POLICY_CLIFF, "Near", date(2026, 9, 1), ""),
        Signal(Kind.POLICY_CLIFF, "Old", date(2023, 1, 1), ""),
        Signal(Kind.POLICY_CLIFF, "Recent", date(2026, 1, 1), ""),
    ], today=TODAY)
    assert [s.label for s in ledger.upcoming] == ["Near", "Far"]
    assert [s.label for s in ledger.passed] == ["Recent", "Old"]


def test_a_sentence_says_how_far_away_the_date_is():
    s = Signal(Kind.POLICY_CLIFF, "A scheme closes", date(2026, 9, 1),
               "After this it is unavailable.", impact=Money("50000"))
    said = s.sentence(TODAY)
    assert "19 days away" in said
    assert "Worth ₹50,000" in said


def test_a_date_that_has_passed_reads_as_passed():
    s = Signal(Kind.POLICY_CLIFF, "A scheme closed", date(2026, 8, 1), "")
    assert "passed on 01 August 2026, 12 days ago" in s.sentence(TODAY)


def test_serialises_with_the_impact_and_the_years():
    d = Signal(Kind.OBSERVED_PATTERN, "Clearance", None, "Stock cleared.",
               years_observed=(2021, 2022)).to_dict(TODAY)
    assert d["impact"] is None
    assert d["years_observed"] == [2021, 2022]
    assert d["is_a_forecast"] is False
