"""Chapter VI-A deductions — CORE-006.

Each test names the v1 defect it prevents from returning. Every one of those
defects OVERSTATED a deduction, which is the dangerous direction: a user acts
on it, claims it, and finds out during assessment.
"""

from __future__ import annotations

import pytest

from backend.core.provenance.money import ZERO, Money, rupees
from backend.core.rules import load_ruleset
from backend.core.tax_engine.deductions import (
    DeductionClaim,
    compute_80ccd2,
    compute_80cce_group,
    compute_80d,
    compute_80ddb,
    compute_disability,
    compute_hra_exemption,
    compute_interest_deduction,
    filter_by_regime,
)

RS = load_ruleset("2026-27")


# ── 80D: a four-way matrix, not v1's flat ₹1,50,000 ─────────────────────────

@pytest.mark.parametrize(
    "self_senior,parents_senior,expected",
    [
        (False, False, 50_000),   # 25k + 25k
        (True, False, 75_000),    # 50k + 25k
        (False, True, 75_000),    # 25k + 50k
        (True, True, 100_000),    # 50k + 50k — the only route to the ceiling
    ],
)
def test_80d_matrix(self_senior: bool, parents_senior: bool, expected: int) -> None:
    out = compute_80d(
        DeductionClaim(
            "80D", rupees(60_000),
            self_is_senior=self_senior,
            parents_are_senior=parents_senior,
            parents_premium=rupees(60_000),
        ),
        RS,
    )
    assert out.allowed == Money(expected)


def test_80d_never_reaches_v1s_150000() -> None:
    """₹1,50,000 appears nowhere in s.80D. The true maximum is ₹1,00,000."""
    out = compute_80d(
        DeductionClaim("80D", rupees(500_000), self_is_senior=True,
                       parents_are_senior=True, parents_premium=rupees(500_000)),
        RS,
    )
    assert out.allowed == Money(100_000)
    assert out.disallowed == Money(900_000)


def test_80d_preventive_checkup_is_within_the_cap_not_additional() -> None:
    at_cap = compute_80d(
        DeductionClaim("80D", rupees(25_000), parents_premium=rupees(25_000),
                       preventive_checkup=rupees(5_000)),
        RS,
    )
    assert at_cap.allowed == Money(50_000), "check-up must not exceed the caps"

    with_room = compute_80d(
        DeductionClaim("80D", rupees(20_000), parents_premium=rupees(20_000),
                       preventive_checkup=rupees(5_000)),
        RS,
    )
    assert with_room.allowed == Money(45_000), "check-up uses available headroom"


# ── 80CCE: one shared ceiling, which v1 handed out twice ────────────────────

def test_80cce_is_one_shared_ceiling() -> None:
    out = compute_80cce_group(
        {"80C": rupees(150_000), "80CCD_1": rupees(150_000)}, RS
    )
    assert out.allowed == Money(150_000), "v1 allowed ₹3,00,000 here"
    assert out.claimed == Money(300_000)
    assert any("80CCE" in n for n in out.notes)


def test_80cce_partial_use() -> None:
    out = compute_80cce_group({"80C": rupees(90_000), "80CCC": rupees(30_000)}, RS)
    assert out.allowed == Money(120_000)
    assert out.notes == []


def test_80cce_empty() -> None:
    assert compute_80cce_group({}, RS).allowed == ZERO


# ── 80CCD(2): the new regime's biggest lever, missing from v1 ───────────────

def test_80ccd2_rate_differs_by_regime() -> None:
    salary = rupees(1_500_000)
    contribution = rupees(300_000)
    assert compute_80ccd2(contribution, salary, RS, "new").allowed == Money(210_000)
    assert compute_80ccd2(contribution, salary, RS, "old").allowed == Money(150_000)


def test_80ccd2_government_employee_gets_14pc_in_either_regime() -> None:
    out = compute_80ccd2(
        rupees(300_000), rupees(1_500_000), RS, "old", is_government_employee=True
    )
    assert out.allowed == Money(210_000)


def test_80ccd2_capped_at_actual_contribution() -> None:
    out = compute_80ccd2(rupees(50_000), rupees(1_500_000), RS, "new")
    assert out.allowed == Money(50_000)


# ── 80DDB: age-conditional, which v1 ignored ────────────────────────────────

@pytest.mark.parametrize("senior,expected", [(False, 40_000), (True, 90_000)])
def test_80ddb_depends_on_patient_age(senior: bool, expected: int) -> None:
    out = compute_80ddb(
        DeductionClaim("80DDB", rupees(90_000), patient_is_senior=senior), RS
    )
    assert out.allowed == Money(expected)


def test_80ddb_senior_ceiling() -> None:
    out = compute_80ddb(
        DeductionClaim("80DDB", rupees(250_000), patient_is_senior=True), RS
    )
    assert out.allowed == Money(100_000)


# ── 80U / 80DD: flat amounts, not reimbursements ────────────────────────────

@pytest.mark.parametrize("code", ["80U", "80DD"])
@pytest.mark.parametrize("severe,expected", [(False, 75_000), (True, 125_000)])
def test_disability_is_a_flat_amount(code: str, severe: bool, expected: int) -> None:
    out = compute_disability(
        code, DeductionClaim(code, ZERO, severe_disability=severe), RS
    )
    assert out.allowed == Money(expected)


# ── 80TTA vs 80TTB: mutually exclusive, chosen by age ───────────────────────

def test_under_60_gets_80tta_on_savings_interest_only() -> None:
    out = compute_interest_deduction(rupees(15_000), rupees(80_000), 45, RS)
    assert out.allowed == Money(10_000)
    assert "does not qualify" in out.steps[0].note


def test_senior_gets_80ttb_across_all_deposit_interest() -> None:
    out = compute_interest_deduction(rupees(15_000), rupees(80_000), 65, RS)
    assert out.allowed == Money(50_000)


def test_boundary_at_exactly_60() -> None:
    assert compute_interest_deduction(ZERO, rupees(80_000), 59, RS).allowed == ZERO
    assert compute_interest_deduction(ZERO, rupees(80_000), 60, RS).allowed == Money(50_000)


# ── HRA: least of three ─────────────────────────────────────────────────────

def test_hra_takes_the_least_of_three() -> None:
    out = compute_hra_exemption(
        rupees(600_000), rupees(300_000), rupees(240_000), True, RS
    )
    # HRA 300,000 · rent−10% salary = 240,000−60,000 = 180,000 · 50% = 300,000
    assert out.allowed == Money(180_000)
    assert out.notes and "taxable" in out.notes[0]


def test_hra_metro_vs_non_metro() -> None:
    args = (rupees(600_000), rupees(400_000), rupees(500_000))
    metro = compute_hra_exemption(*args, True, RS).allowed
    non_metro = compute_hra_exemption(*args, False, RS).allowed
    assert metro == Money(300_000)      # 50% of salary binds
    assert non_metro == Money(240_000)  # 40% of salary binds
    assert non_metro < metro


def test_hra_with_no_rent_paid_is_nil() -> None:
    out = compute_hra_exemption(rupees(600_000), rupees(300_000), ZERO, True, RS)
    assert out.allowed == ZERO


def test_hra_fully_exempt_leaves_no_note() -> None:
    out = compute_hra_exemption(rupees(600_000), rupees(100_000), rupees(400_000), True, RS)
    assert out.allowed == Money(100_000)
    assert out.notes == []


# ── regime gate ─────────────────────────────────────────────────────────────

def test_regime_filter_reports_rather_than_silently_dropping() -> None:
    kept, rejected = filter_by_regime(
        {"80C": rupees(150_000), "80D": rupees(25_000), "80CCD_2": rupees(100_000)},
        RS,
        "new",
    )
    assert set(kept) == {"80CCD_2"}
    assert len(rejected) == 2
    assert all("not available" in r for r in rejected)


def test_regime_filter_old_allows_chapter_via() -> None:
    kept, rejected = filter_by_regime(
        {"80C": rupees(150_000), "80D": rupees(25_000)}, RS, "old"
    )
    assert set(kept) == {"80C", "80D"}
    assert rejected == []


def test_regime_filter_skips_zero_claims() -> None:
    kept, rejected = filter_by_regime({"80C": ZERO}, RS, "old")
    assert kept == {} and rejected == []
