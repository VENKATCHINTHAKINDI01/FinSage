"""Loss set-off and harvesting — PLN-003.

The claims worth testing here are not "the arithmetic adds up". They are:

  * a loss is never spent on the exempt slice of s.112A LTCG, because that
    saves nothing and the loss is gone
  * the constrained loss (LTCL) is used before the flexible one (STCL)
  * current-year losses go before brought-forward ones
  * a harvesting suggestion is never made where there is nothing to gain
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from backend.core.provenance.money import ZERO, rupees
from backend.core.rules import load_ruleset
from backend.core.tax_engine.harvesting import (
    GainBucket as B,
)
from backend.core.tax_engine.harvesting import (
    Position,
    bucket_rate,
    exempt_floor,
    harvest,
    set_off_losses,
)

FY = "2026-27"
RS = load_ruleset(FY)
EXEMPTION = rupees(125_000)


def _set_off(gains, **kw):
    return set_off_losses(gains, FY, **kw)


# ══ the exemption is a rate, not a deduction ════════════════════════════════

class TestTheExemptSliceIsNeverSpentOn:
    """The central claim of the module. Everything else is bookkeeping."""

    def test_the_floor_is_the_statutory_exemption(self) -> None:
        assert exempt_floor(B.EQUITY_LTCG_112A, RS) == EXEMPTION
        assert exempt_floor(B.EQUITY_STCG_111A, RS) == ZERO
        assert exempt_floor(B.OTHER_LTCG_112, RS) == ZERO

    def test_a_loss_stops_at_the_exempt_floor(self) -> None:
        """₹2,00,000 of equity LTCG offers ₹75,000 of headroom, not ₹2,00,000.
        With ₹2,50,000 of STCL available the allocator uses ₹1,00,000 on the
        STCG and ₹75,000 on the LTCG, then stops — leaving ₹1,25,000 of gain
        standing because it is taxed at nothing."""
        r = _set_off(
            {B.EQUITY_LTCG_112A: 200_000, B.EQUITY_STCG_111A: 100_000},
            stcl=250_000,
        )
        assert r.gains_after[B.EQUITY_LTCG_112A] == EXEMPTION
        assert r.unused_stcl == rupees(75_000)
        assert r.exempt_slice_preserved == EXEMPTION

    def test_the_preserved_loss_is_worth_more_than_the_tax_it_would_have_saved(
        self,
    ) -> None:
        """Spending it would have saved ₹0 and cost ₹75,000 of carry-forward."""
        r = _set_off({B.EQUITY_LTCG_112A: 200_000}, stcl=250_000)
        assert r.tax_saved == rupees(9_375)          # 75,000 × 12.5%
        assert r.unused_stcl == rupees(175_000)

    def test_gains_entirely_within_the_exemption_attract_no_set_off_at_all(self) -> None:
        r = _set_off({B.EQUITY_LTCG_112A: 100_000}, stcl=100_000)
        assert r.allocations == []
        assert r.tax_saved == ZERO
        assert r.unused_stcl == rupees(100_000)

    def test_the_user_is_told_why_the_gain_was_left_alone(self) -> None:
        r = _set_off({B.EQUITY_LTCG_112A: 200_000}, stcl=250_000)
        assert any("that is deliberate" in n for n in r.notes)


# ══ ordering by rate ════════════════════════════════════════════════════════

class TestRateOrdering:
    def test_a_scarce_loss_goes_to_the_most_heavily_taxed_gain(self) -> None:
        """₹50,000 of STCL against ₹1,00,000 of 20% STCG and ₹2,00,000 of
        12.5% LTCG. Into the STCG it saves ₹10,000; into the LTCG, ₹6,250.
        The ₹3,750 difference is the whole feature."""
        r = _set_off(
            {B.EQUITY_LTCG_112A: 200_000, B.EQUITY_STCG_111A: 100_000},
            stcl=50_000,
        )
        assert len(r.allocations) == 1
        assert r.allocations[0].bucket is B.EQUITY_STCG_111A
        assert r.tax_saved == rupees(10_000)

    def test_slab_taxed_gains_outrank_everything_at_the_top_bracket(self) -> None:
        r = _set_off(
            {B.OTHER_STCG_SLAB: 100_000, B.EQUITY_STCG_111A: 100_000},
            stcl=50_000, slab_rate=Decimal("0.30"),
        )
        assert r.allocations[0].bucket is B.OTHER_STCG_SLAB
        assert r.tax_saved == rupees(15_000)

    def test_but_not_for_a_taxpayer_in_a_lower_bracket(self) -> None:
        """The caller knows the marginal rate and this module does not.
        Defaulting to 30% would overstate the benefit for everyone below the
        top bracket — at 5% the equity STCG is the better target."""
        r = _set_off(
            {B.OTHER_STCG_SLAB: 100_000, B.EQUITY_STCG_111A: 100_000},
            stcl=50_000, slab_rate=Decimal("0.05"),
        )
        assert r.allocations[0].bucket is B.EQUITY_STCG_111A
        assert r.tax_saved == rupees(10_000)

    def test_the_rate_table_comes_from_the_rule_pack(self) -> None:
        assert bucket_rate(B.EQUITY_STCG_111A, RS) == Decimal("0.20")
        assert bucket_rate(B.EQUITY_LTCG_112A, RS) == Decimal("0.125")
        assert bucket_rate(B.OTHER_LTCG_112, RS) == Decimal("0.125")


# ══ what a loss is allowed to touch ═════════════════════════════════════════

class TestStatutoryConstraints:
    def test_a_long_term_loss_cannot_touch_short_term_gains(self) -> None:
        """s.74(1)(b). The engine must leave the STCG standing and carry the
        LTCL forward rather than take the larger saving."""
        r = _set_off({B.EQUITY_STCG_111A: 100_000}, ltcl=100_000)
        assert r.allocations == []
        assert r.unused_ltcl == rupees(100_000)
        assert r.gains_after[B.EQUITY_STCG_111A] == rupees(100_000)

    def test_a_short_term_loss_may_touch_either(self) -> None:
        """s.74(1)(a)."""
        r = _set_off({B.OTHER_LTCG_112: 100_000}, stcl=100_000)
        assert r.allocations[0].bucket is B.OTHER_LTCG_112
        assert r.unused_stcl == ZERO

    def test_the_constrained_loss_is_spent_first(self) -> None:
        """Both losses could cover the LTCG, but only the STCL can reach the
        STCG. Spending the STCL on the LTCG would strand the LTCL entirely.

        LTCL → the ₹1,00,000 of taxable other-LTCG; STCL → the ₹1,00,000 STCG.
        Everything is used and nothing is stranded.
        """
        r = _set_off(
            {B.OTHER_LTCG_112: 100_000, B.EQUITY_STCG_111A: 100_000},
            stcl=100_000, ltcl=100_000,
        )
        by_kind = {a.loss_kind: a.bucket for a in r.allocations}
        assert by_kind["LTCL"] is B.OTHER_LTCG_112
        assert by_kind["STCL"] is B.EQUITY_STCG_111A
        assert r.unused_stcl == ZERO and r.unused_ltcl == ZERO
        assert r.tax_saved == rupees(32_500)      # 12,500 + 20,000

    def test_the_flexible_loss_is_what_gets_carried_forward(self) -> None:
        """Where only one loss can be used, the engine leaves the taxpayer
        holding the STCL — the one with more future options."""
        r = _set_off({B.OTHER_LTCG_112: 100_000}, stcl=100_000, ltcl=100_000)
        assert r.unused_ltcl == ZERO
        assert r.unused_stcl == rupees(100_000)


# ══ carry-forward ═══════════════════════════════════════════════════════════

class TestCarryForward:
    def test_current_year_losses_are_used_before_brought_forward_ones(self) -> None:
        """ss.70/71 run before s.74. It matters: a brought-forward loss is
        already partway through its eight-year window."""
        r = _set_off(
            {B.EQUITY_STCG_111A: 100_000}, stcl=100_000, brought_forward_stcl=100_000
        )
        assert len(r.allocations) == 1
        assert r.allocations[0].from_brought_forward is False
        assert r.unused_stcl == rupees(100_000)

    def test_brought_forward_losses_are_used_when_current_year_runs_out(self) -> None:
        r = _set_off(
            {B.EQUITY_STCG_111A: 100_000}, stcl=40_000, brought_forward_stcl=100_000
        )
        assert [a.from_brought_forward for a in r.allocations] == [False, True]
        assert r.allocations[1].amount == rupees(60_000)

    def test_the_eight_year_window_and_its_condition_are_stated(self) -> None:
        r = _set_off({B.EQUITY_STCG_111A: 10_000}, stcl=100_000)
        note = next(n for n in r.notes if "carry forward" in n)
        assert "8 assessment years" in note
        assert "filed by the due date" in note

    def test_the_asymmetry_of_the_two_loss_types_is_explained(self) -> None:
        r = _set_off({B.EQUITY_STCG_111A: 10_000}, ltcl=100_000)
        assert any("only ever be set off against" in n for n in r.notes)


def test_the_ordering_caveat_separates_the_statutory_from_the_chosen() -> None:
    """The constraints are law and are stated as such; the ordering is a
    reading and is stated as such. Collapsing the two — in either direction —
    is what makes a caveat useless."""
    for kwargs in ({"stcl": 100_000}, {"ltcl": 100_000}, {}):
        r = _set_off({B.EQUITY_STCG_111A: 100_000}, **kwargs)
        note = next(n for n in r.notes if "fixed by statute" in n)
        assert "applied here exactly" in note
        assert "not specified by s.70" in note
        assert "most favourable to you" in note


def test_the_worksheet_and_citations_survive_serialisation() -> None:
    d = _set_off({B.EQUITY_STCG_111A: 100_000}, stcl=50_000).to_dict()
    assert d["tax_saved"] == "10000.00"
    assert d["carried_forward_stcl"] == "0.00"
    assert {c["legacy_section"] for c in d["citations"]} == {"70", "74"}


# ══ holding periods ═════════════════════════════════════════════════════════

class TestPosition:
    def test_twelve_months_to_the_day_is_long_term(self) -> None:
        p = Position("INFY", date(2026, 4, 10), rupees(100), rupees(200))
        assert p.is_long_term_on(date(2027, 4, 10), 12)

    def test_one_day_short_is_not(self) -> None:
        """The most expensive day in retail investing: 20% instead of 12.5%."""
        p = Position("INFY", date(2026, 4, 10), rupees(100), rupees(200))
        assert not p.is_long_term_on(date(2027, 4, 9), 12)

    def test_the_countdown_is_reported(self) -> None:
        p = Position("INFY", date(2026, 4, 10), rupees(100), rupees(200))
        assert p.days_to_long_term(date(2027, 4, 1), 12) == 9
        assert p.days_to_long_term(date(2027, 5, 1), 12) == 0


# ══ harvesting ══════════════════════════════════════════════════════════════

FEB = date(2027, 2, 1)


def _pos(name, acquired, cost, value):
    return Position(name, acquired, rupees(cost), rupees(value))


class TestHarvesting:
    def test_gain_harvesting_is_capped_by_the_unused_exemption(self) -> None:
        """₹80,000 already realised leaves ₹45,000 of exemption. A position
        sitting on ₹2,00,000 of gain should be told to take ₹45,000, not
        ₹2,00,000."""
        plan = harvest(
            [_pos("INFY", date(2020, 1, 1), 100_000, 300_000)],
            FY, as_of=FEB, realised_equity_ltcg=80_000,
        )
        gain = next(o for o in plan.opportunities if o.kind == "harvest_gain")
        assert gain.amount == rupees(45_000)
        assert plan.exemption_remaining == ZERO

    def test_the_exemption_is_shared_across_positions_not_applied_per_holding(
        self,
    ) -> None:
        plan = harvest(
            [
                _pos("INFY", date(2020, 1, 1), 100_000, 200_000),
                _pos("TCS", date(2020, 1, 1), 100_000, 200_000),
            ],
            FY, as_of=FEB,
        )
        taken = sum(
            (o.amount for o in plan.opportunities if o.kind == "harvest_gain"),
            ZERO,
        )
        assert taken == EXEMPTION

    def test_no_gain_harvesting_once_the_exemption_is_spent(self) -> None:
        plan = harvest(
            [_pos("INFY", date(2020, 1, 1), 100_000, 300_000)],
            FY, as_of=FEB, realised_equity_ltcg=125_000,
        )
        assert not any(o.kind == "harvest_gain" for o in plan.opportunities)

    def test_a_short_term_holding_is_not_offered_for_gain_harvesting(self) -> None:
        """The exemption is a s.112A concession. Realising a short-term gain
        to 'use' it would trigger 20% tax instead of nothing."""
        plan = harvest([_pos("NEW", date(2026, 12, 1), 100_000, 200_000)], FY, as_of=FEB)
        assert not any(o.kind == "harvest_gain" for o in plan.opportunities)

    def test_loss_harvesting_is_not_suggested_where_there_is_nothing_to_offset(
        self,
    ) -> None:
        """Advice to pay brokerage for no tax benefit. The carry-forward is
        real but does not justify an unprompted suggestion."""
        plan = harvest([_pos("XYZ", date(2020, 1, 1), 200_000, 100_000)], FY, as_of=FEB)
        assert not any(o.kind == "harvest_loss" for o in plan.opportunities)

    def test_loss_harvesting_is_quantified_against_booked_gains(self) -> None:
        plan = harvest(
            [_pos("XYZ", date(2020, 1, 1), 200_000, 100_000)],
            FY, as_of=FEB, realised_equity_stcg=200_000,
        )
        loss = next(o for o in plan.opportunities if o.kind == "harvest_loss")
        assert loss.amount == rupees(100_000)
        assert loss.tax_effect == rupees(12_500)     # long-term loss, 12.5%

    def test_a_holding_close_to_long_term_is_flagged_to_wait(self) -> None:
        """₹1,00,000 of gain, 20% now versus 12.5% in a few weeks — ₹7,500."""
        plan = harvest([_pos("ABC", date(2026, 4, 10), 100_000, 200_000)],
                       FY, as_of=date(2027, 3, 1))
        wait = next(o for o in plan.opportunities if o.kind == "wait")
        assert wait.tax_effect == rupees(7_500)
        assert "12.5% long-term" in wait.rationale

    def test_opportunities_are_ordered_by_what_they_are_worth(self) -> None:
        plan = harvest(
            [
                _pos("SMALL", date(2020, 1, 1), 100_000, 110_000),
                _pos("BIG", date(2020, 1, 1), 100_000, 300_000),
            ],
            FY, as_of=FEB,
        )
        effects = [o.tax_effect for o in plan.opportunities]
        assert effects == sorted(effects, reverse=True)

    def test_the_deadline_is_the_end_of_the_financial_year(self) -> None:
        plan = harvest([_pos("INFY", date(2020, 1, 1), 100_000, 300_000)],
                       FY, as_of=FEB)
        assert plan.opportunities[0].act_by == date(2027, 3, 31)


class TestHarvestingCaveats:
    def test_the_repurchase_caution_is_always_present(self) -> None:
        """The acceptance criterion, and the note most likely to keep a user
        out of trouble.

        The claim is sourced: India genuinely has no wash-sale rule, and GAAR
        is the only limit. An earlier draft said same-day repurchase "has been
        challenged as lacking commercial substance", which overstated how often
        GAAR reaches retail share transactions."""
        plan = harvest([], FY, as_of=FEB)
        note = next(n for n in plan.notes if "wash-sale" in n)
        assert "India has no wash-sale rule" in note
        assert "General Anti-Avoidance Rules" in note
        assert "very rarely" in note

    def test_the_use_it_or_lose_it_nature_of_the_exemption_is_stated(self) -> None:
        plan = harvest([], FY, as_of=FEB)
        assert any("does not carry forward" in n for n in plan.notes)

    def test_tax_effect_is_not_presented_as_investment_return(self) -> None:
        plan = harvest([], FY, as_of=FEB)
        assert any("not whether the underlying investment" in n for n in plan.notes)

    def test_an_empty_portfolio_produces_no_suggestions_but_still_advises(self) -> None:
        plan = harvest([], FY, as_of=FEB)
        assert plan.opportunities == []
        assert plan.total_tax_effect == ZERO
        assert plan.notes

    def test_serialises(self) -> None:
        d = harvest([_pos("INFY", date(2020, 1, 1), 100_000, 300_000)],
                    FY, as_of=FEB).to_dict()
        assert d["opportunities"][0]["kind"] == "harvest_gain"
        assert d["as_of"] == "2027-02-01"


@pytest.mark.parametrize("fy", ["2024-25", "2025-26", "2026-27"])
def test_prior_years_load_their_own_exemption(fy: str) -> None:
    """The exemption is read from the rule pack, not hardcoded — revised
    returns for earlier years have to keep working."""
    rs = load_ruleset(fy)
    assert exempt_floor(B.EQUITY_LTCG_112A, rs) > ZERO


# ══ golden corpus ═══════════════════════════════════════════════════════════

def _golden() -> list[dict]:
    import pathlib

    import yaml

    path = pathlib.Path(__file__).parent / "golden" / "harvesting" / "fy_2026_27.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


GOLDEN = _golden()


@pytest.mark.parametrize("case", GOLDEN, ids=[c["id"] for c in GOLDEN])
def test_golden_set_off(case: dict) -> None:
    r = set_off_losses(
        {B(k): rupees(v) for k, v in case["gains"].items()},
        FY,
        stcl=rupees(case.get("stcl", 0)),
        ltcl=rupees(case.get("ltcl", 0)),
        brought_forward_stcl=rupees(case.get("brought_forward_stcl", 0)),
        brought_forward_ltcl=rupees(case.get("brought_forward_ltcl", 0)),
        slab_rate=Decimal(case.get("slab_rate", "0.30")),
    )
    actual = {
        "tax_saved": r.tax_saved,
        "allocations": len(r.allocations),
        "carried_forward_stcl": r.unused_stcl,
        "carried_forward_ltcl": r.unused_ltcl,
        "gains_after_ltcg": r.gains_after.get(B.EQUITY_LTCG_112A, ZERO),
        "first_bucket": r.allocations[0].bucket.value if r.allocations else None,
    }
    mismatches = []
    for key, want in case["expect"].items():
        assert key in actual, f"{case['id']}: unknown expectation {key!r}"
        got = actual[key]
        ok = got == want if isinstance(want, str) or key == "allocations" else got == rupees(want)
        if not ok:
            mismatches.append(f"    {key}: expected {want}, got {got}")
    if mismatches:
        pytest.fail(
            f"\n{case['id']}\n" + "\n".join(mismatches)
            + f"\n  verified against: {case['verified_against'].strip()}"
        )


def test_every_golden_case_shows_its_working() -> None:
    for case in GOLDEN:
        assert case.get("verified_against", "").strip(), f"{case['id']} has none"


def test_the_corpus_exercises_both_constraints_and_both_orderings() -> None:
    """A corpus of only rate-ordering cases would pass with the statutory
    constraints removed entirely."""
    ids = " ".join(c["id"] for c in GOLDEN)
    assert "CANNOT-REACH" in ids           # s.74 constraint
    assert "CONSTRAINED-LOSS-IS-SPENT-FIRST" in ids
    assert "EXEMPT-FLOOR" in ids
    assert "CURRENT-YEAR-BEFORE-BROUGHT-FORWARD" in ids
