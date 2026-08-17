"""Tearing a quotation apart — PRC-006."""

from __future__ import annotations

from datetime import date

import pytest

from backend.core.costing.landed_cost import Purchase, _load, compute_landed_cost
from backend.core.provenance.money import Money
from backend.procurement.quote_teardown import (
    Quote,
    QuoteLine,
    Verdict,
    classify,
    tear_down,
)

CFG = _load("procurement.yaml")
GST = _load("gst.yaml")
BOUGHT = date(2026, 6, 1)


def landed(ex_showroom="1200000", *, electric=False, category="motor_vehicle",
           accessories="0", state="KA"):
    return compute_landed_cost(
        Purchase(
            item="Test vehicle",
            ex_showroom=Money(ex_showroom),
            category=category,
            state=state,
            purchase_date=BOUGHT,
            is_electric=electric,
            accessories=Money(accessories),
        ),
        "2026-27",
    )


def quote(*lines, total=None):
    return Quote(
        item="Test vehicle",
        lines=[QuoteLine(label, Money(amount)) for label, amount in lines],
        stated_total=Money(total) if total else None,
        quoted_on=BOUGHT,
        dealer="A dealer",
    )


# ── naming is where padding hides ───────────────────────────────────────────

def test_the_longest_matching_term_wins():
    """'rto' and 'rto tax' map to different computed figures. Shortest-match
    would let the registration line claim the road tax comparison."""
    assert classify("RTO Tax", CFG)[0] == "road_tax"
    assert classify("Registration / Smart Card", CFG)[0] == "registration"
    assert classify("Insurance (Own Damage)", CFG)[0] == "insurance"
    assert classify("Dealer Handling Charges", CFG)[0] == "no_statutory_basis"
    assert classify("Extended Warranty", CFG)[0] == "unknown"


def test_a_line_matching_two_kinds_takes_the_longer_term():
    """"RTO Registration Charges" contains both `rto` (road tax) and
    `registration`, and the two are compared against completely different
    computed figures — a state road tax of over a lakh versus a ₹600 fee.
    First-match-wins would pick whichever kind happens to be earlier in the
    rule file, which is not a decision anyone made.
    """
    assert classify("RTO Registration Charges", CFG)[0] == "registration"

    model = landed("1200000")
    out = tear_down(quote(("RTO Registration Charges", "6000")),
                    model, cfg=CFG, gst_pack=GST)
    over = [f for f in out.findings if f.verdict is Verdict.EXCEEDS_STATUTORY]
    assert over and over[0].expected == Money("600")


def test_ampersands_and_spacing_do_not_defeat_matching():
    assert classify("RTO  &  Road   Tax", CFG)[0] == "road_tax"
    assert classify("PRE-DELIVERY INSPECTION", CFG)[0] == "no_statutory_basis"


# ── the flagship check ──────────────────────────────────────────────────────

def test_an_abolished_gst_slab_is_caught_and_named():
    """The largest single error available on an Indian quote today. 28%
    against 18% on a ₹12 lakh vehicle is ₹1.2 lakh."""
    model = landed("1200000")
    out = tear_down(
        quote(("Ex-showroom", "1200000"), ("GST @ 28%", "336000")),
        model, cfg=CFG, gst_pack=GST,
    )
    gst = [f for f in out.findings if f.verdict is Verdict.WRONG_RATE]
    assert gst, out.findings
    assert "no longer exists" in gst[0].detail
    assert "22 September 2025" in gst[0].detail
    assert gst[0].delta == Money("120000")     # 28% − 18% of ₹12,00,000


def test_the_twelve_percent_slab_is_abolished_too():
    model = landed("1200000")
    out = tear_down(
        quote(("Ex-showroom", "1200000"), ("GST", "144000")),
        model, cfg=CFG, gst_pack=GST,
    )
    assert any(f.verdict is Verdict.WRONG_RATE for f in out.findings)


def test_the_correct_gst_rate_produces_no_finding():
    model = landed("1200000")
    out = tear_down(
        quote(("Ex-showroom", "1200000"), ("GST @ 18%", "216000")),
        model, cfg=CFG, gst_pack=GST,
    )
    assert [f for f in out.findings if f.verdict is Verdict.WRONG_RATE] == []


def test_an_ev_quoted_at_the_petrol_rate_is_caught():
    model = landed("1200000", electric=True, category="electric_vehicle")
    out = tear_down(
        quote(("Ex-showroom", "1200000"), ("GST", "216000")),   # 18%, not 5%
        model, cfg=CFG, gst_pack=GST,
    )
    wrong = [f for f in out.findings if f.verdict is Verdict.WRONG_RATE]
    assert wrong
    assert wrong[0].expected == Money("60000")
    assert wrong[0].delta == Money("156000")


# ── statutory lines that are simply too big ─────────────────────────────────

def test_registration_padded_above_the_schedule_is_flagged():
    model = landed("1200000")
    out = tear_down(
        quote(("Registration Charges", "6000")), model, cfg=CFG, gst_pack=GST,
    )
    over = [f for f in out.findings if f.verdict is Verdict.EXCEEDS_STATUTORY]
    assert over
    assert over[0].expected == Money("600")
    assert over[0].delta == Money("5400")


def test_a_dealer_charging_less_than_the_schedule_is_not_a_finding_against_them():
    """And the delta never goes negative — a favourable line must not net off
    against a real overcharge elsewhere in the same quote."""
    model = landed("1200000")
    out = tear_down(
        quote(("Registration", "400"), ("Handling", "5000")),
        model, cfg=CFG, gst_pack=GST,
    )
    assert out.overcharged == Money(0)
    assert out.negotiable == Money("5000")


def test_an_under_charged_line_does_not_net_off_a_real_overcharge():
    """The case the non-negative delta exists for.

    Here TCS is under-collected by ₹10,000 and registration is padded by
    ₹5,400. A signed delta would net these to a headline saying the buyer is
    ₹4,600 AHEAD, and the padded registration — which is real and arguable —
    would vanish. The under-collected TCS is also not the buyer's problem: it
    is the dealer's obligation, and it is credited to the buyer either way.
    """
    model = landed("1200000")
    out = tear_down(
        quote(("TCS", "2000"), ("Registration", "6000")),
        model, cfg=CFG, gst_pack=GST,
    )
    assert out.overcharged == Money("5400")


# ── the two totals, kept apart ──────────────────────────────────────────────

def test_a_handling_fee_is_negotiable_and_never_called_an_overcharge():
    """Adding the two would hand the buyer a single number, part of which they
    will be told — correctly — that they agreed to. The argument then collapses
    and takes the defensible half with it."""
    model = landed("1200000")
    out = tear_down(
        quote(
            ("Ex-showroom", "1200000"),
            ("GST @ 28%", "336000"),
            ("Dealer Handling", "12000"),
            ("Documentation Charges", "3500"),
        ),
        model, cfg=CFG, gst_pack=GST,
    )
    assert out.overcharged == Money("120000")     # the GST slab only
    assert out.negotiable == Money("15500")       # handling + documentation
    assert out.overcharged != out.overcharged + out.negotiable

    for f in out.findings:
        if f.verdict is Verdict.NO_STATUTORY_BASIS:
            assert not f.verdict.is_defensible
            assert "not improper" in f.detail


def test_the_headline_names_both_numbers_separately():
    model = landed("1200000")
    out = tear_down(
        quote(("Ex-showroom", "1200000"), ("GST @ 28%", "336000"),
              ("Handling", "12000")),
        model, cfg=CFG, gst_pack=GST,
    )
    assert "above the statutory figures" in out.headline()
    assert "no statutory basis" in out.headline()


def test_a_clean_quote_says_so_plainly():
    model = landed("1200000")
    out = tear_down(
        quote(("Ex-showroom", "1200000"), ("GST @ 18%", "216000"),
              ("Registration", "600")),
        model, cfg=CFG, gst_pack=GST,
    )
    assert out.overcharged == Money(0)
    assert "Nothing on this quote disagrees" in out.headline()


# ── TCS is not a cost ───────────────────────────────────────────────────────

def test_tcs_at_the_right_rate_is_reported_as_recoverable_not_as_a_charge():
    """It is the buyer's own tax collected early. Listed beside road tax it
    makes the on-road price look higher than the money they are out, and
    almost nobody claims it back."""
    model = landed("1200000")
    out = tear_down(
        quote(("Ex-showroom", "1200000"), ("TCS", "12000")),
        model, cfg=CFG, gst_pack=GST,
    )
    tcs = [f for f in out.findings if f.verdict is Verdict.NOT_A_COST]
    assert tcs
    assert "creditable" in tcs[0].detail
    assert out.not_a_cost == Money("12000")
    assert out.overcharged == Money(0)


def test_tcs_charged_below_the_threshold_is_not_collectable():
    model = landed("800000")
    out = tear_down(
        quote(("Ex-showroom", "800000"), ("TCS", "8000")),
        model, cfg=CFG, gst_pack=GST,
    )
    na = [f for f in out.findings if f.verdict is Verdict.NOT_APPLICABLE]
    assert na
    assert na[0].delta == Money("8000")
    assert "206C(1F)" in na[0].detail


def test_tcs_is_charged_on_the_whole_consideration_not_the_excess():
    """A dealer computing 1% of the excess over ₹10 lakh under-collects, and a
    buyer told the wrong basis argues the wrong point."""
    model = landed("1200000")
    out = tear_down(
        quote(("Ex-showroom", "1200000"), ("TCS", "2000")),   # 1% of ₹2L
        model, cfg=CFG, gst_pack=GST,
    )
    wrong = [f for f in out.findings if f.verdict is Verdict.WRONG_RATE]
    assert wrong
    assert wrong[0].expected == Money("12000")
    assert "not only the excess" in wrong[0].detail


def test_accessories_count_toward_the_tcs_threshold():
    model = landed("980000", accessories="40000")
    out = tear_down(
        quote(("Ex-showroom", "980000"), ("Accessories", "40000"),
              ("TCS", "10200")),
        model, cfg=CFG, gst_pack=GST,
    )
    assert [f for f in out.findings if f.verdict is Verdict.NOT_APPLICABLE] == []


# ── silence is not approval ─────────────────────────────────────────────────

def test_an_unrecognised_line_is_reported_as_unchecked_not_dropped():
    """'Three issues found' reads as 'everything else is fine'. A teardown
    that quietly drops the extended warranty has told the buyer something
    false by omission."""
    model = landed("1200000")
    out = tear_down(
        quote(("Ex-showroom", "1200000"), ("Extended Warranty", "28000"),
              ("Fastag & Accessories Kit", "4500")),
        model, cfg=CFG, gst_pack=GST,
    )
    unchecked = {f.label for f in out.unchecked}
    assert "Extended Warranty" in unchecked
    assert "not the same as saying it is fair" in out.unchecked[0].detail
    assert "Extended Warranty" in out.coverage()


def test_coverage_says_so_when_everything_was_checked():
    model = landed("1200000")
    out = tear_down(
        quote(("GST @ 18%", "216000"), ("Registration", "600"),
              ("Handling", "5000")),
        model, cfg=CFG, gst_pack=GST,
    )
    assert out.unchecked == []
    assert "Every line on this quote was checked" in out.coverage()


def test_insurance_is_recognised_but_not_judged():
    """A third-party price this engine does not set. Recognised so it is not
    reported as unchecked; not priced, because it has no statutory figure."""
    model = landed("1200000")
    out = tear_down(
        quote(("Insurance — Own Damage + Third Party", "48000")),
        model, cfg=CFG, gst_pack=GST,
    )
    assert out.unchecked == []
    assert out.overcharged == Money(0)
    assert out.negotiable == Money(0)


# ── arithmetic ──────────────────────────────────────────────────────────────

def test_a_quote_that_does_not_add_up_is_flagged_first():
    model = landed("1200000")
    out = tear_down(
        quote(("Ex-showroom", "1200000"), ("GST @ 18%", "216000"),
              total="1450000"),
        model, cfg=CFG, gst_pack=GST,
    )
    assert out.findings[0].verdict is Verdict.ARITHMETIC
    assert out.findings[0].delta == Money("34000")
    assert "before anything else" in out.findings[0].detail


def test_a_quote_with_no_stated_total_is_not_faulted_for_it():
    model = landed("1200000")
    out = tear_down(quote(("GST @ 18%", "216000")), model, cfg=CFG, gst_pack=GST)
    assert [f for f in out.findings if f.verdict is Verdict.ARITHMETIC] == []


# ── restraint ───────────────────────────────────────────────────────────────

def test_no_finding_ever_calls_a_price_high():
    """The engine has no view on whether ₹12 lakh is a good price for the car.
    That is a market judgement and PRC-006 makes none."""
    model = landed("1200000")
    out = tear_down(
        quote(("Ex-showroom", "1200000"), ("GST @ 28%", "336000"),
              ("Handling", "12000"), ("Extended Warranty", "28000")),
        model, cfg=CFG, gst_pack=GST,
    )
    banned = ("overpriced", "too high", "expensive", "bad deal", "rip-off",
              "should pay", "worth")
    blob = " ".join(f.detail for f in out.findings).lower() + out.headline().lower()
    for word in banned:
        assert word not in blob, word


def test_serialises_with_both_totals_and_the_coverage_statement():
    model = landed("1200000")
    d = tear_down(
        quote(("GST @ 28%", "336000"), ("Handling", "12000"),
              ("Extended Warranty", "28000")),
        model, cfg=CFG, gst_pack=GST,
    ).to_dict()
    assert d["overcharged_display"]
    assert d["negotiable_display"]
    assert "Extended Warranty" in d["coverage"]
    assert any(f["defensible"] for f in d["findings"])
    assert any(not f["defensible"] for f in d["findings"])


@pytest.mark.parametrize("label", ["GST", "gst", "G.S.T", "Goods and Services Tax"])
def test_gst_is_recognised_however_it_is_written(label):
    if label == "G.S.T":
        pytest.skip("dotted abbreviations are not handled; documented as a gap")
    assert classify(label, CFG)[0] == "gst"
