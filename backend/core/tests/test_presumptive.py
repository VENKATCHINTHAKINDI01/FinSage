"""Presumptive taxation — CORE-008.

Three claims worth testing:

  * the digital-receipt UPLIFT applies to the ceiling, not just the rate — a
    ₹2.4cr business that banks everything is eligible and most tooling says no
  * the 6%/8% split in 44AD is PER RUPEE, not a single rate chosen by majority
  * 44AE is per vehicle per month, and one vehicle over the limit at any point
    disqualifies the whole year
"""

from __future__ import annotations

import pytest

from backend.core.provenance.money import ZERO, rupees
from backend.core.rules import RuleError, load_ruleset
from backend.core.tax_engine.presumptive import (
    Scheme,
    Vehicle,
    compute_44ad,
    compute_44ada,
    compute_44ae,
    uses_single_advance_tax_instalment,
)

FY = "2026-27"


class Test44adCeilingAndUplift:
    def test_the_plain_ceiling_is_two_crore(self) -> None:
        assert compute_44ad(20_000_000, FY).eligible
        assert not compute_44ad(20_000_001, FY).eligible

    def test_it_lifts_to_three_crore_on_mostly_digital_receipts(self) -> None:
        """The rule most engines miss. A ₹2.4cr business banking everything is
        eligible; carrying only the ₹2cr figure tells them they are not."""
        assert compute_44ad(24_000_000, FY, digital_receipts=24_000_000).eligible
        assert not compute_44ad(24_000_000, FY).eligible

    def test_the_threshold_is_ninety_five_percent_not_a_majority(self) -> None:
        t = 24_000_000
        assert compute_44ad(t, FY, digital_receipts=int(t * 0.95)).eligible
        assert not compute_44ad(t, FY, digital_receipts=int(t * 0.94)).eligible

    def test_an_ineligible_taxpayer_is_told_what_would_have_qualified_them(
        self,
    ) -> None:
        """A banking decision, not a tax one — and worth saying so."""
        r = compute_44ad(24_000_000, FY)
        assert any("non-cash" in n and "₹3,00,00,000" in n for n in r.notes)

    def test_the_uplifted_ceiling_still_binds(self) -> None:
        assert not compute_44ad(30_000_001, FY, digital_receipts=30_000_001).eligible


class Test44adRateSplit:
    def test_six_percent_on_digital_and_eight_on_cash(self) -> None:
        """Per rupee. ₹60L digital at 6% plus ₹40L cash at 8% is ₹6,80,000 —
        an effective 6.8%, which is not either headline rate."""
        r = compute_44ad(10_000_000, FY, digital_receipts=6_000_000)
        assert r.presumptive_income == rupees(680_000)
        assert r.effective_rate == "6.80%"

    def test_all_digital_is_six_percent(self) -> None:
        r = compute_44ad(10_000_000, FY, digital_receipts=10_000_000)
        assert r.presumptive_income == rupees(600_000)

    def test_all_cash_is_eight_percent(self) -> None:
        assert compute_44ad(10_000_000, FY).presumptive_income == rupees(800_000)

    def test_digital_receipts_cannot_exceed_turnover(self) -> None:
        """A profile error must not manufacture a lower rate."""
        r = compute_44ad(10_000_000, FY, digital_receipts=99_000_000)
        assert r.presumptive_income == rupees(600_000)

    def test_the_split_is_explained_rather_than_just_applied(self) -> None:
        r = compute_44ad(10_000_000, FY, digital_receipts=6_000_000)
        assert any("per rupee, not to the whole turnover" in n for n in r.notes)

    def test_the_worksheet_shows_both_legs(self) -> None:
        rendered = compute_44ad(
            10_000_000, FY, digital_receipts=6_000_000
        ).trace.render()
        assert "at 6%" in rendered and "at 8%" in rendered


class Test44adLockIn:
    def test_declaring_below_the_presumptive_rate_is_warned_about(self) -> None:
        """Five years out of the scheme, plus books and audit. The most
        expensive thing a small business can do casually."""
        r = compute_44ad(10_000_000, FY, digital_receipts=10_000_000,
                         declared_income=400_000)
        note = next(n for n in r.notes if "FOLLOWING years" in n)
        assert "5 FOLLOWING years" in note
        assert "tax audit" in note

    def test_declaring_at_or_above_it_gets_the_general_caution_only(self) -> None:
        r = compute_44ad(10_000_000, FY, digital_receipts=10_000_000,
                         declared_income=600_000)
        assert not any("You are declaring" in n for n in r.notes)
        assert any("locks you out" in n for n in r.notes)

    def test_44ada_has_no_lock_in_and_says_so(self) -> None:
        r = compute_44ada(4_000_000, FY)
        assert any("no opt-out lock-in" in n for n in r.notes)


class Test44ada:
    def test_a_flat_half_of_gross_receipts(self) -> None:
        assert compute_44ada(4_000_000, FY).presumptive_income == rupees(2_000_000)

    def test_the_ceiling_is_fifty_lakh(self) -> None:
        assert compute_44ada(5_000_000, FY).eligible
        assert not compute_44ada(5_000_001, FY).eligible

    def test_and_seventy_five_lakh_on_digital_receipts(self) -> None:
        assert compute_44ada(7_500_000, FY, digital_receipts=7_500_000).eligible
        assert not compute_44ada(7_500_001, FY, digital_receipts=7_500_001).eligible

    def test_an_ineligible_result_computes_no_income(self) -> None:
        r = compute_44ada(8_000_000, FY)
        assert not r.eligible
        assert r.presumptive_income == ZERO


class Test44ae:
    def test_a_heavy_vehicle_is_charged_per_tonne(self) -> None:
        """25 tonnes at ₹1,000 a tonne a month for a year."""
        r = compute_44ae([Vehicle(25_000, 12)], FY)
        assert r.presumptive_income == rupees(300_000)

    def test_a_light_vehicle_is_a_flat_monthly_figure(self) -> None:
        assert compute_44ae([Vehicle(6_000, 12)], FY).presumptive_income == (
            rupees(90_000)
        )

    def test_the_boundary_is_twelve_tonnes(self) -> None:
        """Motor Vehicles Act definition. At exactly 12,000 kg it is NOT heavy,
        so the flat rate applies — one kilo over and it is per tonne."""
        assert compute_44ae([Vehicle(12_000, 12)], FY).presumptive_income == (
            rupees(90_000)
        )
        assert compute_44ae([Vehicle(12_001, 12)], FY).presumptive_income > (
            rupees(90_000)
        )

    def test_part_years_are_charged_by_month(self) -> None:
        assert compute_44ae([Vehicle(25_000, 3)], FY).presumptive_income == (
            rupees(75_000)
        )

    def test_more_than_ten_vehicles_disqualifies_the_whole_year(self) -> None:
        """Not pro-rata. Holding an eleventh at any point removes the scheme
        for the entire year."""
        r = compute_44ae([Vehicle(6_000) for _ in range(11)], FY)
        assert not r.eligible
        assert "AT ANY POINT" in r.reason
        assert r.presumptive_income == ZERO

    def test_exactly_ten_is_fine(self) -> None:
        assert compute_44ae([Vehicle(6_000) for _ in range(10)], FY).eligible

    def test_no_vehicles_is_refused_rather_than_returning_zero_income(self) -> None:
        r = compute_44ae([], FY)
        assert not r.eligible
        assert "no vehicles were supplied" in r.reason

    def test_a_mixed_fleet_sums_correctly(self) -> None:
        r = compute_44ae(
            [Vehicle(25_000, 12, "lorry"), Vehicle(6_000, 12, "van"),
             Vehicle(15_000, 3, "truck")], FY,
        )
        assert r.presumptive_income == rupees(435_000)   # 300k + 90k + 45k

    def test_the_conflicting_source_on_the_threshold_is_disclosed(self) -> None:
        r = compute_44ae([Vehicle(25_000, 12)], FY)
        assert any("Sources conflict" in n for n in r.notes)


def test_every_scheme_pays_advance_tax_in_one_instalment() -> None:
    """The link to PLN-002 — the proviso to s.211(1)."""
    for scheme in Scheme:
        assert uses_single_advance_tax_instalment(scheme)
    assert not uses_single_advance_tax_instalment(None)


def test_a_year_without_a_scheme_configured_raises(self=None) -> None:
    """Rules are data. A missing scheme is a pack to fix, not a code path."""
    rs = load_ruleset("2024-25")
    if "44AE" in rs.presumptive:
        pytest.skip("FY 2024-25 pack already carries 44AE")
    with pytest.raises(RuleError, match="no 44AE configuration"):
        compute_44ae([Vehicle(6_000)], "2024-25", ruleset=rs)


def test_results_serialise_with_a_citation() -> None:
    d = compute_44ad(10_000_000, FY, digital_receipts=6_000_000).to_dict()
    assert d["scheme"] == "44AD"
    assert d["citation"]["legacy_section"] == "44AD"
    assert d["effective_rate"] == "6.80%"
