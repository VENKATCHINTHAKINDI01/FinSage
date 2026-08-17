"""The admission gate — PRC-010.

Each test here corresponds to one way the gate could be quietly removed. The
suite is written so that deleting any single check in `admission.py` fails at
least one test, because a gate nobody has tried to break is a gate nobody knows
works.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from backend.core.provenance.admission import (
    CandidateFact,
    Verdict,
    admit,
    admit_all,
    facts_for_costing,
    load_admission_rules,
    parse_money,
    parse_rate,
    tier_for,
)
from backend.core.provenance.money import Money
from backend.core.provenance.sourcing import CostLine, Tier, Tier3CannotCost

CFG = load_admission_rules()
SEEN = date(2026, 8, 13)


def candidate(**kw) -> CandidateFact:
    base = {
        "key": "gst.electric_vehicle",
        "raw_value": "5%",
        "value_kind": "rate",
        "extracted_by": "html_table_cell",
        "source_url": "https://cbic.gov.in/gst-rates",
        "fetched_on": SEEN,
        "source_kind": "gst",
    }
    base.update(kw)
    return CandidateFact(**base)


# ── the crossing itself ─────────────────────────────────────────────────────

def test_a_clean_official_candidate_is_admitted_and_can_cost():
    a = admit("gst.electric_vehicle", [candidate()])
    assert a.verdict is Verdict.ADMITTED
    assert a.may_cost
    assert a.fact.value == Decimal("0.05")
    assert a.fact.tier is Tier.OFFICIAL
    # The whole point: the promoted fact is accepted by the constructor that
    # refuses everything else.
    line = CostLine("GST at 5%", Money("75000"), a.fact)
    assert line.amount == Money("75000")


def test_a_candidate_is_not_a_fact_and_cannot_be_costed():
    """The type boundary, asserted rather than assumed.

    If `CandidateFact` ever grows the attributes `CostLine` reads, this stops
    raising and the gate becomes optional.
    """
    with pytest.raises(AttributeError):
        CostLine("GST", Money("75000"), candidate())  # type: ignore[arg-type]


def test_an_undated_candidate_cannot_even_be_constructed():
    with pytest.raises(ValueError, match="no fetch date"):
        candidate(fetched_on=None)


# ── 1. who lifted the number ────────────────────────────────────────────────

def test_a_figure_the_model_read_is_rejected_at_tier_1():
    """The governing rule. An official URL does not launder a model-authored
    number: the provenance of the figure is still 'a model said so'."""
    a = admit("gst.electric_vehicle", [candidate(extracted_by="llm_stated")])
    assert a.verdict is Verdict.REJECTED
    assert a.fact is None
    assert "language model" in a.gap.reason


def test_a_model_authored_figure_is_not_even_shown_as_context():
    """Badging does not cure a hallucination; it gives it a place on the page.

    Contrast with the Tier-3 case below, which IS shown as context.
    """
    a = admit(
        "gst.electric_vehicle",
        [candidate(extracted_by="agent_recall",
                   source_url="https://someblog.example/gst")],
    )
    assert a.verdict is Verdict.REJECTED


def test_a_deterministic_candidate_survives_a_model_authored_sibling():
    a = admit("gst.electric_vehicle", [
        candidate(extracted_by="llm_summary", raw_value="12%"),
        candidate(extracted_by="regex_rate", raw_value="5%"),
    ])
    assert a.verdict is Verdict.ADMITTED
    assert a.fact.value == Decimal("0.05")


# ── 2. parsing ──────────────────────────────────────────────────────────────

def test_a_bare_number_is_refused_because_it_is_ambiguous():
    """'5' on a page may mean five, or five per cent. Refusing is the only
    honest reading, and guessing per cent is how a 500% rate gets shipped."""
    assert parse_rate("5") is None
    assert parse_rate("5%") == Decimal("0.05")
    assert parse_rate("5 per cent") == Decimal("0.05")
    assert parse_rate("0.05") == Decimal("0.05")


def test_indian_number_words_parse():
    assert parse_money("₹1,50,000") == Money("150000")
    assert parse_money("Rs. 1.5 lakh") == Money("150000")
    assert parse_money("INR 2 crore") == Money("20000000")
    assert parse_money("no figure here") is None


def test_an_unparseable_extraction_is_a_verdict_not_an_exception():
    a = admit("gst.electric_vehicle", [candidate(raw_value="see table below")])
    assert a.verdict is Verdict.REJECTED
    assert "did not parse" in a.gap.reason


# ── 3. plausibility ─────────────────────────────────────────────────────────

def test_an_abolished_gst_slab_is_refused():
    """GST 2.0 left four slabs. A page still quoting 12% is out of date or is
    describing a pre-September-2025 transaction; either way it must not
    silently become a cost line."""
    a = admit("gst.laptop", [candidate(key="gst.laptop", raw_value="12%")])
    assert a.verdict is Verdict.REJECTED
    assert any("not one of the permitted values" in c.detail
               for c in a.failed())


def test_the_four_live_gst_slabs_all_pass():
    for raw, expected in [("0%", "0"), ("5%", "0.05"),
                          ("18%", "0.18"), ("40%", "0.40")]:
        a = admit("gst.laptop", [candidate(key="gst.laptop", raw_value=raw)])
        assert a.verdict is Verdict.ADMITTED, raw
        assert a.fact.value == Decimal(expected)


def test_a_figure_out_of_band_is_refused():
    """The band exists to catch the extractor that grabbed the loan interest
    rate instead of the stamp duty."""
    a = admit("stamp_duty.MH", [
        candidate(key="stamp_duty.MH", raw_value="42%", source_kind="stamp_duty",
                  source_url="https://igrmaharashtra.gov.in/x"),
        candidate(key="stamp_duty.MH", raw_value="42%", source_kind="stamp_duty",
                  source_url="https://maharashtra.gov.in/y"),
    ])
    assert a.verdict is Verdict.REJECTED


def test_a_key_with_no_plausibility_rule_is_quarantined_not_waved_through():
    """Unscreened is quarantined by default. If the default were 'allow', every
    new key would be trusted until someone remembered to add a band."""
    a = admit("mystery_levy.KA", [
        candidate(key="mystery_levy.KA", raw_value="7%"),
    ])
    assert a.verdict is Verdict.REJECTED
    assert "no plausibility rule" in " ".join(c.detail for c in a.failed())


def test_zero_road_tax_is_plausible_because_ev_exemptions_are_real():
    a = admit("road_tax.KA.ev", [
        candidate(key="road_tax.KA.ev", raw_value="0%",
                  source_kind="road_tax",
                  source_url="https://parivahan.gov.in/kar"),
    ])
    assert a.verdict is Verdict.ADMITTED
    assert a.fact.value == Decimal("0")


# ── 4. tier from the domain ─────────────────────────────────────────────────

def test_tier_comes_from_the_host_not_from_a_claim_about_it():
    assert tier_for("https://cbic.gov.in/x", CFG) is Tier.OFFICIAL
    assert tier_for("https://transport.karnataka.gov.in/x", CFG) is Tier.OFFICIAL
    assert tier_for("https://www.sbi.co.in/rates", CFG) is Tier.OEM_OR_BANK
    assert tier_for("https://cardekho.example/price", CFG) is Tier.AGGREGATOR


def test_an_unknown_domain_defaults_down_never_up():
    """The default direction matters more than the table. Defaulting upward
    means every new source is trusted until someone notices."""
    assert tier_for("https://totally-new-site.example/gst", CFG) is Tier.AGGREGATOR
    assert tier_for("not a url at all", CFG) is Tier.AGGREGATOR
    assert tier_for("", CFG) is Tier.AGGREGATOR


def test_a_lookalike_domain_does_not_match_by_containment():
    """`gov.in.evil.example` contains 'gov.in'. Suffix matching is on a dot
    boundary precisely so it does not resolve to Tier-1."""
    assert tier_for("https://gov.in.evil.example/gst", CFG) is Tier.AGGREGATOR


def test_a_clean_tier_3_figure_is_context_only_and_still_cannot_cost():
    a = admit("gst.laptop", [
        candidate(key="gst.laptop", raw_value="18%",
                  source_url="https://marketplace.example/listing"),
    ])
    assert a.verdict is Verdict.CONTEXT_ONLY
    assert not a.may_cost
    assert a.fact is not None                 # it is shown
    assert a.gap is not None                  # and the gap is still named
    with pytest.raises(Tier3CannotCost):      # but it cannot be totalled
        CostLine("GST", Money("18000"), a.fact)


def test_an_official_source_outranks_an_aggregator_that_disagrees():
    a = admit("gst.laptop", [
        candidate(key="gst.laptop", raw_value="40%",
                  source_url="https://marketplace.example/listing"),
        candidate(key="gst.laptop", raw_value="18%",
                  source_url="https://cbic.gov.in/rates"),
    ])
    assert a.verdict is Verdict.ADMITTED
    assert a.fact.value == Decimal("0.18")


# ── 5. corroboration ────────────────────────────────────────────────────────

def test_one_official_page_is_enough_for_a_statutory_rate():
    """A rate published by the department that levies it is not made truer by
    a second copy of it."""
    a = admit("gst.electric_vehicle", [candidate()])
    assert a.verdict is Verdict.ADMITTED


def test_a_locality_figure_needs_two_independent_hosts():
    one = candidate(key="stamp_duty.MH", raw_value="6%",
                    source_kind="stamp_duty",
                    source_url="https://igrmaharashtra.gov.in/a")
    a = admit("stamp_duty.MH", [one])
    assert a.verdict is Verdict.REJECTED
    assert "only 1 source" in a.gap.reason

    b = admit("stamp_duty.MH", [
        one,
        candidate(key="stamp_duty.MH", raw_value="6%",
                  source_kind="stamp_duty",
                  source_url="https://maharashtra.gov.in/igr"),
    ])
    assert b.verdict is Verdict.ADMITTED
    assert b.fact.value == Decimal("0.06")


def test_two_pages_on_one_site_are_one_source():
    """Independence is by host. Counting pages would let a single site satisfy
    a quorum of two by being linked twice."""
    a = admit("stamp_duty.MH", [
        candidate(key="stamp_duty.MH", raw_value="6%", source_kind="stamp_duty",
                  source_url="https://igrmaharashtra.gov.in/a"),
        candidate(key="stamp_duty.MH", raw_value="6%", source_kind="stamp_duty",
                  source_url="https://igrmaharashtra.gov.in/b"),
    ])
    assert a.verdict is Verdict.REJECTED


def test_www_and_bare_host_are_the_same_source():
    a = admit("stamp_duty.MH", [
        candidate(key="stamp_duty.MH", raw_value="6%", source_kind="stamp_duty",
                  source_url="https://igrmaharashtra.gov.in/a"),
        candidate(key="stamp_duty.MH", raw_value="6%", source_kind="stamp_duty",
                  source_url="https://www.igrmaharashtra.gov.in/b"),
    ])
    assert a.verdict is Verdict.REJECTED


def test_sources_that_disagree_produce_a_gap_not_an_average():
    """The failure mode this whole codebase exists to avoid. Averaging 5% and
    7% gives 6%, which is authoritative-looking and true nowhere."""
    a = admit("stamp_duty.MH", [
        candidate(key="stamp_duty.MH", raw_value="5%", source_kind="stamp_duty",
                  source_url="https://igrmaharashtra.gov.in/a"),
        candidate(key="stamp_duty.MH", raw_value="7%", source_kind="stamp_duty",
                  source_url="https://maharashtra.gov.in/b"),
    ])
    assert a.verdict is Verdict.REJECTED
    assert a.fact is None
    assert "do not agree" in a.gap.reason


def test_money_agreement_allows_a_small_percentage_gap():
    two_pct_apart = admit("circle_rate.MH.andheri", [
        candidate(key="circle_rate.MH.andheri", raw_value="₹1,00,000",
                  value_kind="money", source_kind="circle_rate",
                  source_url="https://igrmaharashtra.gov.in/a"),
        candidate(key="circle_rate.MH.andheri", raw_value="₹1,01,000",
                  value_kind="money", source_kind="circle_rate",
                  source_url="https://maharashtra.gov.in/b"),
    ])
    assert two_pct_apart.verdict is Verdict.ADMITTED

    far_apart = admit("circle_rate.MH.andheri", [
        candidate(key="circle_rate.MH.andheri", raw_value="₹1,00,000",
                  value_kind="money", source_kind="circle_rate",
                  source_url="https://igrmaharashtra.gov.in/a"),
        candidate(key="circle_rate.MH.andheri", raw_value="₹1,40,000",
                  value_kind="money", source_kind="circle_rate",
                  source_url="https://maharashtra.gov.in/b"),
    ])
    assert far_apart.verdict is Verdict.REJECTED


# ── gaps are the deliverable of a failure ───────────────────────────────────

def test_nothing_found_still_produces_a_named_gap():
    a = admit("stamp_duty.TR", [])
    assert a.verdict is Verdict.REJECTED
    assert a.gap.candidates_seen == 0
    assert "not included" in a.gap.sentence()
    assert a.gap.what_would_fix_it


def test_facts_for_costing_returns_both_halves():
    """A caller that took only the usable half would silently drop the gaps,
    which is the behaviour the design refuses. Returning a tuple makes the
    omission visible at the call site."""
    results = admit_all({
        "gst.electric_vehicle": [candidate()],
        "stamp_duty.MH": [candidate(key="stamp_duty.MH", raw_value="6%",
                                    source_kind="stamp_duty",
                                    source_url="https://igrmaharashtra.gov.in/a")],
        "gst.laptop": [candidate(key="gst.laptop", raw_value="18%",
                                 source_url="https://marketplace.example/x")],
    })
    usable, gaps = facts_for_costing(results)
    assert set(usable) == {"gst.electric_vehicle"}
    assert {g.key for g in gaps} == {"stamp_duty.MH", "gst.laptop"}


def test_admission_serialises_with_its_working_shown():
    a = admit("gst.electric_vehicle", [candidate()])
    d = a.to_dict()
    assert d["verdict"] == "admitted"
    assert d["may_cost"] is True
    assert [c["name"] for c in d["checks"]] == [
        "deterministic_extractor", "parsed", "plausible", "tier",
        "corroborated",
    ]


# ── misuse ──────────────────────────────────────────────────────────────────

def test_mixing_keys_raises_rather_than_corroborating():
    with pytest.raises(ValueError, match="Mixing"):
        admit("gst.laptop", [candidate(key="road_tax.KA")])


def test_mixing_a_rate_with_an_amount_raises():
    with pytest.raises(ValueError, match="disagree on what they are"):
        admit("gst.laptop", [
            candidate(key="gst.laptop", raw_value="18%"),
            candidate(key="gst.laptop", raw_value="₹18,000", value_kind="money"),
        ])
