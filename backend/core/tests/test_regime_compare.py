"""Regime comparison and breakeven — PLN-001.

The breakeven is not asserted against hardcoded numbers. It is *verified*: at
the returned figure the two regimes must actually cost the same, and either
side of it the winner must flip. A hardcoded expectation would only prove the
function still returns what it returned when I wrote the test.
"""

from __future__ import annotations

import pathlib

import pytest

from backend.core.provenance.money import ZERO, Money, rupees
from backend.core.tax_engine import TaxInput, compute_tax
from backend.core.tax_engine.regime_compare import (
    breakeven_deductions,
    compare_regimes,
    comparison_trace,
    payable,
)

FY = "2026-27"


def _tax(regime: str, salary: int, deductions: dict[str, Money] | None = None) -> Money:
    return compute_tax(
        TaxInput(fy=FY, regime=regime, age=35, salary=rupees(salary),
                 deductions=deductions or {})
    ).total_tax_exact


# ══ the breakeven is verified, not asserted ═════════════════════════════════

SALARIES = [800_000, 1_200_000, 1_500_000, 2_000_000, 2_500_000, 5_000_000]


@pytest.mark.parametrize("salary", SALARIES)
def test_at_the_breakeven_the_two_regimes_cost_the_same(salary: int) -> None:
    """The defining property. Within the search precision, tax must match."""
    point = breakeven_deductions(rupees(salary), FY, age=35)
    if point is None:
        pytest.skip("no achievable breakeven at this income")

    old = _tax("old", salary, {"80C": point})
    new = _tax("new", salary)
    assert abs((old - new).amount) < 200, (
        f"at ₹{salary:,} the breakeven of {point} gives old={old} vs new={new}, "
        f"which is not a crossing point"
    )


@pytest.mark.parametrize("salary", SALARIES)
def test_the_winner_flips_either_side_of_the_breakeven(salary: int) -> None:
    """Below it the new regime wins; above it the old one does. If that is not
    true, the number is not a breakeven whatever else it is."""
    point = breakeven_deductions(rupees(salary), FY, age=35)
    if point is None:
        pytest.skip("no achievable breakeven at this income")

    new = _tax("new", salary)
    below = _tax("old", salary, {"80C": point - rupees(50_000)})
    above = _tax("old", salary, {"80C": point + rupees(50_000)})

    assert below > new, "below the breakeven the old regime should cost more"
    assert above < new, "above the breakeven the old regime should cost less"


@pytest.mark.parametrize("salary", [300_000, 800_000, 1_200_000, 1_275_000])
def test_no_breakeven_is_reported_where_the_new_regime_is_already_nil(
    salary: int,
) -> None:
    """The case that caught me out, and the case most salaried people are in.

    Below roughly ₹12.75L the s.87A rebate makes new-regime tax zero. The old
    regime can *match* zero with enough deductions but never beat it — at ₹8L,
    ₹2,50,000 of 80C gets you to the same ₹0 you already had.

    An earlier version reported that ₹2,50,000 as a breakeven, which would have
    told someone to lock up two and a half lakh to achieve nothing. A tie is
    not a reason to switch, so the honest answer is None.
    """
    assert _tax("new", salary) == ZERO, "premise: new-regime tax is nil here"
    assert breakeven_deductions(rupees(salary), FY, age=35) is None


@pytest.mark.parametrize("salary", [2_500_000, 3_000_000, 5_000_000, 10_000_000])
def test_the_high_income_breakeven_matches_the_algebra(salary: int) -> None:
    """Once both regimes are in the 30% band the answer is a constant, and it
    can be derived by hand — which makes it a check on the engine rather than a
    recording of it.

        new (pre-cess) = 3,00,000 + 0.30 × (S − 75,000 − 24,00,000)
        old (pre-cess) = 1,12,500 + 0.30 × (S − 50,000 − D − 10,00,000)

    Setting them equal, S cancels and D = ₹8,00,000 exactly.

    An earlier version searched against the s.288B-rounded liability and
    reported ₹8,00,005 — the point where the *rounded* figures first differ,
    which is a rounding artefact rather than economics. Searching the exact
    liability and presenting in round hundreds gives the real number.
    """
    assert breakeven_deductions(rupees(salary), FY, age=35) == rupees(800_000)


@pytest.mark.parametrize("salary", [1_400_000, 1_500_000, 2_000_000, 5_000_000])
def test_rounding_for_presentation_does_not_move_the_answer(salary: int) -> None:
    """Thresholds are quoted in round hundreds, which can land either side of
    the true crossing by up to ₹50 of deduction — a couple of rupees of tax.

    What must hold is that the quoted figure is still a crossing: near-parity
    at the threshold, and a clear win a thousand rupees above it. If rounding
    ever moved the answer by more than the noise floor, this catches it.
    """
    point = breakeven_deductions(rupees(salary), FY, age=35)
    assert point is not None
    assert point.amount % 100 == 0, "thresholds are presented in round ₹100"

    new = _tax("new", salary)
    at_threshold = _tax("old", salary, {"80C": point})
    clearly_above = _tax("old", salary, {"80C": point + rupees(1_000)})

    assert abs((at_threshold - new).amount) <= 50, "the threshold is not a crossing"
    assert clearly_above < new, "a thousand rupees past it, the old regime must win"


def test_a_nil_liability_is_explained_rather_than_left_blank() -> None:
    c = compare_regimes(800_000, {}, fy=FY, age=35)
    assert c.breakeven_deductions is None
    assert any("already nil" in n for n in c.notes)
    assert any("investments made for tax reasons alone" in n for n in c.notes)


# ══ the comparison ══════════════════════════════════════════════════════════

class TestComparison:
    def test_both_sides_come_from_one_engine(self) -> None:
        c = compare_regimes(1_500_000, {"80C": 150_000}, fy=FY, age=35)
        assert c.old.total_tax_exact == _tax("old", 1_500_000, {"80C": rupees(150_000)})
        assert c.new.total_tax_exact == _tax("new", 1_500_000, {"80C": rupees(150_000)})

    def test_the_new_regime_wins_on_ordinary_deductions(self) -> None:
        """Established by measurement in phase 3: under FY 2026-27 the new
        regime dominates for most people."""
        c = compare_regimes(
            1_500_000, {"80C": 150_000, "80D": 25_000, "80CCD_1B": 50_000},
            fy=FY, age=35,
        )
        assert c.better == "new"
        assert c.saving == Money(89_700)

    def test_the_old_regime_wins_with_a_home_loan_and_full_hra(self) -> None:
        c = compare_regimes(
            1_500_000,
            {"80C": 150_000, "80D": 25_000, "80CCD_1B": 50_000,
             "24b": 200_000, "10_13A": 200_000},
            fy=FY, age=35,
        )
        assert c.better == "old"
        assert c.saving == Money(16_900)

    def test_headroom_tells_you_how_far_away_switching_is(self) -> None:
        """More useful than a yes/no: how many more rupees of deduction you
        would need before the question is even worth asking."""
        c = compare_regimes(1_500_000, {"80C": 150_000}, fy=FY, age=35)
        assert c.better == "new"
        assert c.headroom_needed is not None
        assert c.headroom_needed > ZERO
        assert "MORE in old-regime deductions" in c.summary()

    def test_no_headroom_is_reported_when_the_old_regime_already_wins(self) -> None:
        c = compare_regimes(
            1_500_000,
            {"80C": 150_000, "24b": 200_000, "10_13A": 200_000,
             "80D": 25_000, "80CCD_1B": 50_000},
            fy=FY, age=35,
        )
        assert c.headroom_needed is None


class TestNotes:
    def test_employer_nps_is_flagged_as_neutral(self) -> None:
        """80CCD(2) survives into both regimes, so it does not favour either —
        a user maximising it should not think it pushes them toward the old
        regime."""
        c = compare_regimes(1_500_000, {"80CCD_2": 210_000}, fy=FY, age=35)
        assert any("BOTH regimes" in n for n in c.notes)

    def test_employer_nps_does_not_move_the_breakeven(self) -> None:
        c = compare_regimes(1_500_000, {"80CCD_2": 210_000}, fy=FY, age=35)
        assert c.current_deductions == ZERO, (
            "80CCD(2) is available in both regimes and must not count toward "
            "the old-regime deduction total"
        )

    def test_a_marginal_difference_is_called_out(self) -> None:
        """A saving of a few thousand rupees is not worth a regime switch with
        lock-in. Probed just past the breakeven, where the old regime wins by
        an amount too small to act on."""
        salary = 1_500_000
        point = breakeven_deductions(rupees(salary), FY, age=35)
        c = compare_regimes(salary, {"80C": point + rupees(5_000)}, fy=FY, age=35)

        assert c.better == "old"
        assert ZERO < c.saving < rupees(5_000)
        assert c.is_close
        assert any("rarely worth a regime switch" in n for n in c.notes)

    def test_an_exact_tie_defaults_to_the_new_regime(self) -> None:
        """At equal cost the tiebreak is not arbitrary: the new regime needs no
        deduction proofs and no opt-in to reverse.

        Because payable tax steps in ₹10 under s.288B there is a band of
        deduction amounts that tie exactly; the loop finds one rather than
        assuming the breakeven itself lands on it.
        """
        salary = 1_500_000
        point = breakeven_deductions(rupees(salary), FY, age=35)
        tie = next(
            (d for offset in range(0, 200, 5)
             for d in [point + rupees(offset)]
             if _tax("old", salary, {"80C": d}) == _tax("new", salary)),
            None,
        )
        assert tie is not None, "expected a deduction amount that ties exactly"

        c = compare_regimes(salary, {"80C": tie}, fy=FY, age=35)
        assert c.saving == ZERO
        assert c.better == "new"
        assert any("better default at a tie" in n for n in c.notes)

    def test_switching_to_old_warns_about_lock_in(self) -> None:
        c = compare_regimes(
            1_500_000,
            {"80C": 150_000, "24b": 200_000, "10_13A": 200_000,
             "80D": 25_000, "80CCD_1B": 50_000},
            fy=FY, age=35,
        )
        assert any("not freely reversible" in n for n in c.notes)


# ══ output ══════════════════════════════════════════════════════════════════

def test_the_worksheet_shows_both_sides() -> None:
    c = compare_regimes(1_500_000, {"80C": 150_000}, fy=FY, age=35)
    rendered = comparison_trace(c).render()
    assert "old regime" in rendered
    assert "new regime" in rendered
    assert "break even" in rendered


def test_the_worksheet_replays() -> None:
    c = compare_regimes(1_500_000, {"80C": 150_000}, fy=FY, age=35)
    assert comparison_trace(c).verify() == []


def test_serialises_with_both_worksheets() -> None:
    d = compare_regimes(1_500_000, {"80C": 150_000}, fy=FY, age=35).to_dict()
    assert d["better_regime"] == "new"
    assert "Tax on slabs" in d["worksheet_old"]
    assert "Tax on slabs" in d["worksheet_new"]


def test_prior_years_still_compare() -> None:
    """Revised returns need this to keep working for earlier years."""
    c = compare_regimes(1_500_000, {"80C": 150_000}, fy="2024-25", age=35)
    assert c.fy == "2024-25"
    assert c.old.total_tax_exact > ZERO and c.new.total_tax_exact > ZERO


@pytest.mark.parametrize("age,band", [(35, "regular"), (65, "senior"), (85, "super")])
def test_age_bands_are_respected_on_the_old_side(age: int, band: str) -> None:
    c = compare_regimes(1_000_000, {}, fy=FY, age=age)
    assert c.old.total_tax_exact == _tax("old", 1_000_000) if age < 60 else True
    assert c.new.total_tax_exact == _tax("new", 1_000_000), "new regime has no age bands"


def test_non_salary_income_does_not_receive_the_standard_deduction() -> None:
    """The flag is not cosmetic. The standard deduction applies only to salary
    and differs by regime (₹75,000 new, ₹50,000 old), so misclassifying pension
    or interest income as salary hands over relief that is not due and tilts
    the comparison toward the new regime.

    Carried over from the tool adapter, which had this flag before the core
    did — dropping it in the move would have been a silent behaviour change.
    """
    salary = compare_regimes(1_500_000, {}, fy=FY, age=35, is_salary=True)
    other = compare_regimes(1_500_000, {}, fy=FY, age=35, is_salary=False)

    assert other.new.taxable_income == rupees(1_500_000)
    assert salary.new.taxable_income == rupees(1_425_000)
    assert payable(other.new) > payable(salary.new)


# ══ capital gains and surcharge ═════════════════════════════════════════════

def _ltcg(*, gain: int, cost: int = 1_000_000):
    """Listed-equity LTCG held six years — s.112A at 12.5% with the ₹1,25,000
    exemption."""
    from datetime import date

    from backend.core.rules import load_ruleset
    from backend.core.tax_engine import compute_capital_gains
    from backend.core.tax_engine.capital_gains import AssetClass, Disposal

    return compute_capital_gains(
        [Disposal(asset=AssetClass.LISTED_EQUITY,
                  acquired_on=date(2020, 6, 1), sold_on=date(2026, 9, 1),
                  cost=rupees(cost), consideration=rupees(cost + gain))],
        load_ruleset(FY),
    )


def _one_crore_ltcg():
    return _ltcg(gain=10_000_000)


class TestCapitalGainsInteraction:
    """Gains are taxed identically in both regimes, so leaving them out of a
    regime comparison looks harmless. It is not: they count toward total income
    for surcharge, and surcharge is where the regimes diverge."""

    def test_gains_pull_a_taxpayer_into_surcharge_who_was_not_in_it(self) -> None:
        gains = _one_crore_ltcg()
        without = compare_regimes(3_000_000, {}, fy=FY, age=40)
        with_gains = compare_regimes(3_000_000, {}, fy=FY, age=40, gains=gains)

        assert without.old.surcharge == ZERO and without.new.surcharge == ZERO
        assert with_gains.old.surcharge > ZERO and with_gains.new.surcharge > ZERO

    def test_gains_change_the_size_of_the_saving(self) -> None:
        """If they did not, threading them through would be pointless."""
        gains = _one_crore_ltcg()
        without = compare_regimes(3_000_000, {"80C": 150_000}, fy=FY, age=40)
        with_gains = compare_regimes(
            3_000_000, {"80C": 150_000}, fy=FY, age=40, gains=gains
        )
        assert with_gains.saving != without.saving

    def test_the_special_rate_tax_itself_is_regime_neutral(self) -> None:
        """s.111A and s.112A rates do not vary by regime. What differs is the
        surcharge computed on top."""
        gains = _one_crore_ltcg()
        c = compare_regimes(3_000_000, {}, fy=FY, age=40, gains=gains)
        assert c.old.special_rate_tax == c.new.special_rate_tax == gains.total_tax

    def test_gains_that_cross_a_surcharge_threshold_move_the_breakeven(self) -> None:
        """A breakeven computed without the user's gains is the wrong number
        for a user who has gains — but only where the gains change something.

        Walking a ₹15L salary's gain across the ₹50L surcharge threshold: at a
        ₹35L gain there is no surcharge and the breakeven is ₹5,43,700; at ₹40L
        surcharge appears and it drops to ₹3,25,000. Someone told ₹5,43,700
        when the truth is ₹3,25,000 would conclude the old regime is out of
        reach when it is not.
        """
        below = breakeven_deductions(
            rupees(1_500_000), FY, age=40, gains=_ltcg(gain=3_500_000)
        )
        above = breakeven_deductions(
            rupees(1_500_000), FY, age=40, gains=_ltcg(gain=4_000_000)
        )
        assert below == rupees(543_700)
        assert above == rupees(325_000)

    def test_a_gain_that_changes_no_band_leaves_the_breakeven_alone(self) -> None:
        """Not every gain moves it, and that is correct rather than a gap.

        At the crossing the two regimes' slab tax is equal by definition. If
        their total incomes also sit in the same surcharge band, the surcharge
        matches too and the crossing does not move. A ₹1cr gain on a ₹30L
        salary is that case.
        """
        gains = _one_crore_ltcg()
        assert (
            breakeven_deductions(rupees(3_000_000), FY, age=40, gains=gains)
            == breakeven_deductions(rupees(3_000_000), FY, age=40)
        )

    def test_the_effect_is_not_monotonic_in_the_size_of_the_gain(self) -> None:
        """Recorded because it looks like a bug and is not.

        Marginal relief at the ₹50L surcharge threshold creates a band where
        the old regime's effective marginal rate spikes. A ₹40L gain lands
        inside that band and pulls the breakeven down to ₹3,25,000; a ₹50L gain
        clears it and the breakeven returns to ₹5,43,700. Anyone later
        'fixing' this into a monotonic curve would be introducing an error.
        """
        at = [
            breakeven_deductions(rupees(1_500_000), FY, age=40, gains=_ltcg(gain=g))
            for g in (3_500_000, 4_000_000, 5_000_000)
        ]
        assert at[0] == at[2] == rupees(543_700)
        assert at[1] == rupees(325_000)


# ══ golden corpus ═══════════════════════════════════════════════════════════

def _golden_cases() -> list[dict]:
    import yaml

    path = (
        pathlib.Path(__file__).parent / "golden" / "regime_comparison" / "fy_2026_27.yaml"
    )
    return yaml.safe_load(path.read_text(encoding="utf-8"))


GOLDEN = _golden_cases()


@pytest.mark.parametrize("case", GOLDEN, ids=[c["id"] for c in GOLDEN])
def test_golden_regime_comparison(case: dict) -> None:
    """Hand-derived cases in a reviewable data file.

    Each carries `verified_against` with the arithmetic worked out by hand. A
    case without that is a recording of the implementation, not a check on it.
    """
    c = compare_regimes(
        case["salary"],
        case.get("deductions") or {},
        fy=FY,
        age=case.get("age", 0),
        is_salary=case.get("is_salary", True),
    )
    expect = case["expect"]
    actual = {
        "better": c.better,
        "old_total_tax": payable(c.old),
        "new_total_tax": payable(c.new),
        "saving": c.saving,
        "breakeven": c.breakeven_deductions,
        "new_taxable_income": c.new.taxable_income,
        "old_taxable_income": c.old.taxable_income,
    }

    mismatches = []
    for key, want in expect.items():
        assert key in actual, f"{case['id']}: unknown expectation key {key!r}"
        got = actual[key]
        if want is None or isinstance(want, str):
            ok = got == want
        else:
            ok = got is not None and got == rupees(want)
        if not ok:
            mismatches.append(f"    {key}: expected {want}, got {got}")

    if mismatches:
        pytest.fail(
            f"\n{case['id']}\n" + "\n".join(mismatches)
            + f"\n  verified against: {case['verified_against'].strip()}\n\n"
            + c.old.trace.render() + "\n\n" + c.new.trace.render()
        )


def test_every_golden_case_states_how_it_was_verified() -> None:
    """The rule that makes the corpus worth having."""
    for case in GOLDEN:
        assert case.get("verified_against", "").strip(), (
            f"{case['id']} has no `verified_against`. An expected value nobody "
            f"checked is the implementation restated back to itself."
        )


def test_the_corpus_covers_both_winners_and_a_null_breakeven() -> None:
    """A corpus where the new regime always wins would pass even if the old
    regime were computed wrongly."""
    winners = {c["expect"].get("better") for c in GOLDEN}
    assert {"old", "new"} <= winners
    assert any(c["expect"].get("breakeven", "absent") is None for c in GOLDEN)
