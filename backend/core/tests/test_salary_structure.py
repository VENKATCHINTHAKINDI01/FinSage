"""Salary structuring — PLN-006.

The claims that matter:

  * every saving is a recomputation, never amount × marginal rate
  * 80CCD(2) runs to 14% under the new regime and 10% under the old
  * a lever the employer will not deliver is not counted as a saving
  * the HRA answer names the BINDING limb, so "your city moved to 50%" is not
    reported as a saving when the percentage limb is not what constrains you
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.core.provenance.money import ZERO, rupees
from backend.core.rules import load_ruleset
from backend.core.tax_engine import TaxInput, compute_tax
from backend.core.tax_engine.deductions import hra_city_rate
from backend.core.tax_engine.salary_structure import (
    SalaryStructure as S,
)
from backend.core.tax_engine.salary_structure import (
    optimise_salary,
)

FY = "2026-27"
RS = load_ruleset(FY)


def _plan(**kw):
    kw.setdefault("gross_salary", rupees(2_000_000))
    kw.setdefault("basic_salary", rupees(1_000_000))
    return optimise_salary(S(**kw), FY)


def _lever(plan, needle):
    return next(x for x in plan.levers if needle in x.name)


# ══ the eight-city HRA change ═══════════════════════════════════════════════

class TestHraCityList:
    @pytest.mark.parametrize("city", [
        "Mumbai", "Delhi", "Kolkata", "Chennai",
        "Bengaluru", "Hyderabad", "Pune", "Ahmedabad",
    ])
    def test_all_eight_cities_are_at_fifty_percent_for_fy_2026_27(self, city) -> None:
        """Expanded by the Income-tax Rules 2026 — the first change to this
        list in over four decades. Four cities were added: Bengaluru,
        Hyderabad, Pune and Ahmedabad."""
        rate, listed = hra_city_rate(city, RS)
        assert rate == Decimal("0.50")
        assert listed

    @pytest.mark.parametrize("city", ["Jaipur", "Lucknow", "Kochi", "Indore"])
    def test_everywhere_else_stays_at_forty(self, city) -> None:
        assert hra_city_rate(city, RS)[0] == Decimal("0.40")

    @pytest.mark.parametrize("city", ["Bengaluru", "Hyderabad", "Pune", "Ahmedabad"])
    def test_the_four_new_cities_were_still_forty_in_fy_2025_26(self, city) -> None:
        """The expansion applies from FY 2026-27 only. Applying 50% to a
        FY 2025-26 return over-states the exemption and invites a notice."""
        assert hra_city_rate(city, load_ruleset("2025-26"))[0] == Decimal("0.40")

    def test_the_original_metros_were_always_fifty(self, ) -> None:
        assert hra_city_rate("Mumbai", load_ruleset("2025-26"))[0] == Decimal("0.50")

    def test_city_matching_ignores_case_and_padding(self) -> None:
        for spelling in ("bengaluru", "  Bengaluru  ", "BENGALURU"):
            assert hra_city_rate(spelling, RS)[1]

    def test_an_unknown_city_falls_to_forty_rather_than_failing(self) -> None:
        """A typo must not silently become 50%. Forty is the statutory
        residual, so defaulting there is both correct and conservative."""
        assert hra_city_rate("Bengalooru", RS)[0] == Decimal("0.40")


class TestWhichHraLimbBinds:
    """The exemption is the LEAST of three amounts. A city moving to 50% only
    helps where the percentage limb is the binding one — which it usually is
    not."""

    def _hra(self, rent_monthly: int, city: str = "Bengaluru"):
        return _lever(_plan(
            hra_received=rupees(600_000), rent_paid=rupees(rent_monthly * 12),
            city=city, regime="old", basic_salary=rupees(1_200_000),
        ), "rent allowance")

    def test_modest_rent_is_bounded_by_the_rent_limb(self) -> None:
        lever = self._hra(30_000)
        assert "rent paid less 10% of salary" in lever.action
        assert "would not help" in lever.action

    def test_very_high_rent_is_bounded_by_the_hra_actually_received(self) -> None:
        lever = self._hra(80_000)
        assert "HRA actually received" in lever.action

    def test_the_percentage_limb_binds_only_in_a_narrow_band(self) -> None:
        """Basic ₹12L, so 50% is ₹6,00,000 and 40% is ₹4,80,000. With HRA of
        ₹6,00,000 and rent set so the rent limb clears ₹6,00,000, the
        percentage is what decides — and there the city list is decisive."""
        lever = _lever(_plan(
            hra_received=rupees(900_000), rent_paid=rupees(85_000 * 12),
            city="Bengaluru", regime="old", basic_salary=rupees(1_200_000),
        ), "rent allowance")
        assert "% of salary" in lever.action
        assert "decisive" in lever.action

    def test_a_non_listed_city_says_so(self) -> None:
        lever = self._hra(30_000, city="Jaipur")
        assert "Jaipur is not on the 50% list" in lever.reason

    def test_hra_is_unavailable_under_the_new_regime_but_priced_anyway(self) -> None:
        """The number matters for the regime comparison even though it cannot
        be claimed."""
        lever = _lever(_plan(
            hra_received=rupees(600_000), rent_paid=rupees(40_000 * 12),
            city="Pune", regime="new",
        ), "rent allowance")
        assert not lever.available
        assert "only under the old regime" in lever.reason
        assert "regime comparison" in lever.reason


# ══ employer NPS — the lever that survives ══════════════════════════════════

class TestEmployerNps:
    def test_the_ceiling_is_fourteen_percent_under_the_new_regime(self) -> None:
        lever = _lever(_plan(regime="new", employer_will_restructure=True), "NPS")
        assert lever.headroom == rupees(140_000)      # 14% of ₹10,00,000 basic

    def test_and_ten_percent_under_the_old(self) -> None:
        lever = _lever(_plan(regime="old", employer_will_restructure=True), "NPS")
        assert lever.headroom == rupees(100_000)

    def test_a_government_employee_gets_fourteen_in_either_regime(self) -> None:
        lever = _lever(_plan(
            regime="old", is_government_employee=True,
            employer_will_restructure=True,
        ), "NPS")
        assert lever.headroom == rupees(140_000)

    def test_existing_contributions_reduce_the_headroom(self) -> None:
        lever = _lever(_plan(
            regime="new", employer_nps=rupees(100_000),
            employer_will_restructure=True,
        ), "NPS")
        assert lever.headroom == rupees(40_000)

    def test_it_is_flagged_as_needing_the_employer(self) -> None:
        assert _lever(_plan(employer_will_restructure=True), "NPS").needs_employer

    def test_the_saving_is_a_recomputation_not_a_rate_estimate(self) -> None:
        """Checked against a direct recomputation of the whole liability.
        At ₹20L the two happen to agree; the next test finds where they do
        not."""
        plan = _plan(regime="new", employer_will_restructure=True)
        lever = _lever(plan, "NPS")

        def tax(nps):
            return compute_tax(TaxInput(
                fy=FY, regime="new", salary=rupees(2_000_000),
                deductions={"80CCD_2": nps} if nps else {},
            )).total_tax

        assert lever.saving == tax(ZERO) - tax(rupees(140_000))

    def test_where_a_marginal_rate_estimate_would_be_badly_wrong(self) -> None:
        """₹2.1L of employer NPS on a ₹15L salary. The deduction drags taxable
        income into the s.87A marginal-relief zone, so the real saving is
        ₹81,900 — a 30% marginal-rate estimate gives ₹63,000 and a 20.8% one
        gives ₹43,680. Both are wrong, and wrong by more than the fee anyone
        would pay for the advice."""
        plan = optimise_salary(S(
            gross_salary=rupees(1_500_000), basic_salary=rupees(1_500_000),
            regime="new", employer_will_restructure=True,
        ), FY)
        lever = _lever(plan, "NPS")
        assert lever.headroom == rupees(210_000)
        assert lever.saving == rupees(81_900)


# ══ employer constraints are respected ══════════════════════════════════════

class TestEmployerConstraints:
    def test_a_lever_payroll_will_not_move_is_not_counted(self) -> None:
        """A saving the person cannot bank is worse than saying nothing."""
        plan = _plan(regime="new")
        lever = _lever(plan, "NPS")
        assert not lever.available
        assert lever.saving == ZERO
        assert plan.total_saving == ZERO

    def test_but_the_headroom_is_still_shown_so_they_can_go_and_ask(self) -> None:
        lever = _lever(_plan(regime="new"), "NPS")
        assert lever.headroom > ZERO
        assert "costs the employer nothing" in lever.action

    def test_and_the_reason_is_explicit(self) -> None:
        assert "will not restructure" in _lever(_plan(regime="new"), "NPS").reason

    def test_the_summary_does_not_promise_an_unavailable_saving(self) -> None:
        assert "nothing in your salary structure" in _plan(regime="new").summary()


# ══ regime gating ═══════════════════════════════════════════════════════════

class TestRegimeGating:
    @pytest.mark.parametrize("section", ["80C", "80CCD(1B)"])
    def test_old_regime_deductions_are_marked_unavailable_on_the_new(
        self, section
    ) -> None:
        lever = _lever(_plan(regime="new"), section)
        assert not lever.available
        assert lever.saving == ZERO
        assert "does not exist under the new regime" in lever.reason

    def test_but_are_priced_on_the_old_regime(self) -> None:
        lever = _lever(_plan(regime="old"), "80C")
        assert lever.available
        assert lever.saving > ZERO

    def test_a_maxed_deduction_is_not_offered_at_all(self) -> None:
        """Note the section match has to be exact — "80C" is a substring of
        "80CCD(1B)", and a loose check here passes whatever the code does."""
        plan = _plan(regime="old", section_80c=rupees(150_000))
        assert "80C" not in {x.section for x in plan.levers}
        assert "80CCD(1B)" in {x.section for x in plan.levers}

    def test_the_new_regime_note_points_at_the_regime_comparison(self) -> None:
        assert any("exact breakeven" in n for n in _plan(regime="new").notes)


# ══ output ══════════════════════════════════════════════════════════════════

def test_available_levers_sort_ahead_of_unavailable_ones() -> None:
    plan = _plan(regime="old", employer_will_restructure=True)
    available = [x.available for x in plan.levers]
    assert available == sorted(available, reverse=True)


def test_the_recomputation_discipline_is_stated_to_the_user() -> None:
    assert any("not from multiplying by a marginal rate" in n
               for n in _plan().notes)


def test_serialises_with_citations() -> None:
    d = _plan(regime="old", employer_will_restructure=True).to_dict()
    assert d["levers"]
    assert {c["legacy_section"] for c in d["citations"]} >= {"80CCD", "10(13A)"}


def test_a_bare_profile_produces_no_false_levers() -> None:
    plan = optimise_salary(S(gross_salary=rupees(400_000)), FY)
    assert plan.tax_now == ZERO
    assert plan.total_saving == ZERO
