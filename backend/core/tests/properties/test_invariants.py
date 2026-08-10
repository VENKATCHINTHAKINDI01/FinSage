"""Layer 2 — property-based invariants — CORE-012.

Golden cases prove specific numbers. Properties prove statements that must hold
for *every* input, which is how cliff bugs get caught without anyone thinking
to write the case that would expose them.

A note on getting the invariant right
--------------------------------------
The obvious property is "post-tax income is monotonic in income". It is wrong,
and the first run of this suite proved it: three apparent cliffs appeared at
₹50L, ₹1cr and ₹2cr.

Checking the law rather than the code resolved it. Marginal relief bounds the
increase in *income tax plus surcharge*. Cess is then levied at 4% on the
relieved figure, so inside a relief zone the pre-cess marginal rate is exactly
100% and the all-in rate is 104% — take-home genuinely does dip a little. That
is the statute working as designed, not a defect.

So the correct invariants are:

    total tax is monotonic non-decreasing              (always)
    income − (tax + surcharge) is monotonic            (what relief guarantees)
    the all-in marginal rate never exceeds 100% + cess (the ceiling relief sets)

Two of those would have passed a naive implementation. The middle one is the
one that actually catches a missing marginal relief.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

pytest.importorskip("hypothesis", reason="hypothesis is a dev dependency")

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from backend.core.provenance.money import ZERO, Money
from backend.core.rules import load_ruleset
from backend.core.tax_engine import TaxInput, compute_tax

FY = "2026-27"
CESS = load_ruleset(FY).cess_rate
MAX_MARGINAL = Decimal("1") + CESS   # 104% — the ceiling marginal relief sets

SLOW = settings(
    max_examples=300,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)

# Taxable income is rounded to the nearest ₹10 by legacy s.288A, so sampling
# arbitrary rupee amounts creates phantom ₹1 gaps between inputs that map to
# the same taxable income. Sample on the ₹10 grid the engine actually uses.
def _grid(lo: int, hi: int) -> st.SearchStrategy[int]:
    return st.integers(min_value=lo // 10, max_value=hi // 10).map(lambda n: n * 10)


# Uniform sampling essentially never lands on a threshold, and thresholds are
# the only place cliffs live.
THRESHOLDS = [
    400_000, 800_000, 1_200_000, 1_600_000, 2_000_000, 2_400_000,
    5_000_000, 10_000_000, 20_000_000, 50_000_000,
]
NEAR_THRESHOLD = st.sampled_from(
    [t + d for t in THRESHOLDS for d in (-10, 0, 10, 1_000, 50_000)]
)

incomes = st.one_of(_grid(0, 30_000_000), NEAR_THRESHOLD)
regimes = st.sampled_from(["new", "old"])


def _result(income: int, regime: str = "new", age: int = 35):
    return compute_tax(
        TaxInput(fy=FY, regime=regime, age=age, other_sources=Money(income))
    )


# ── the invariants ──────────────────────────────────────────────────────────

@SLOW
@given(income=incomes, regime=regimes)
def test_tax_is_never_negative(income: int, regime: str) -> None:
    assert _result(income, regime).total_tax >= ZERO


@SLOW
@given(income=incomes, extra=st.integers(min_value=1, max_value=50_000).map(lambda n: n * 10))
def test_total_tax_is_monotonic(income: int, extra: int) -> None:
    assert _result(income + extra).total_tax >= _result(income).total_tax


@SLOW
@given(income=incomes, extra=st.integers(min_value=1, max_value=20_000).map(lambda n: n * 10))
def test_marginal_relief_bounds_the_pre_cess_liability(income: int, extra: int) -> None:
    """The load-bearing one.

    Marginal relief guarantees that the rise in income tax plus surcharge never
    exceeds the rise in income. Without relief this fails immediately at every
    surcharge threshold — a ₹1.4 lakh jump at ₹50,00,001 in v1's engine.
    """
    before, after = _result(income), _result(income + extra)
    d_income = after.taxable_income - before.taxable_income
    d_liability = after.pre_cess_liability - before.pre_cess_liability
    assert d_liability <= d_income, (
        f"at ₹{income:,} + ₹{extra:,}: tax and surcharge rose by {d_liability} "
        f"for {d_income} more income. Marginal relief is missing or wrong."
    )


@SLOW
@given(income=incomes, extra=st.integers(min_value=1, max_value=20_000).map(lambda n: n * 10))
def test_all_in_marginal_rate_never_exceeds_one_plus_cess(income: int, extra: int) -> None:
    """104% is the ceiling: 100% inside a relief zone, plus cess on top."""
    before, after = _result(income), _result(income + extra)
    d_income = (after.taxable_income - before.taxable_income).amount
    if d_income <= 0:
        return
    d_tax = (after.total_tax - before.total_tax).amount
    assert d_tax <= d_income * MAX_MARGINAL, (
        f"at ₹{income:,}: marginal rate {d_tax / d_income:.4%} exceeds "
        f"{MAX_MARGINAL:.0%}"
    )


@SLOW
@given(
    income=_grid(0, 20_000_000),
    deduction=st.integers(min_value=1, max_value=15_000).map(lambda n: n * 10),
)
def test_deductions_never_increase_tax(income: int, deduction: int) -> None:
    plain = compute_tax(TaxInput(fy=FY, regime="old", other_sources=Money(income)))
    reduced = compute_tax(
        TaxInput(
            fy=FY,
            regime="old",
            other_sources=Money(income),
            deductions={"80C": Money(deduction)},
        )
    )
    assert reduced.total_tax <= plain.total_tax


@SLOW
@given(income=incomes, regime=regimes)
def test_trace_replays_to_the_computed_value(income: int, regime: str) -> None:
    """The worksheet shown to the user must be the computation that ran."""
    result = _result(income, regime)
    assert result.trace.verify() == []


@SLOW
@given(income=incomes)
def test_new_regime_has_no_age_bands(income: int) -> None:
    """v1 switched a 60-year-old to old-regime senior slabs inside a
    new-regime table. Age must make no difference under the new regime."""
    base = _result(income, "new", age=35).total_tax
    for age in (60, 62, 80, 95):
        assert _result(income, "new", age=age).total_tax == base


@SLOW
@given(income=_grid(300_000, 20_000_000))
def test_old_regime_age_bands_only_ever_reduce_tax(income: int) -> None:
    regular = _result(income, "old", age=45).total_tax
    senior = _result(income, "old", age=65).total_tax
    super_senior = _result(income, "old", age=85).total_tax
    assert senior <= regular
    assert super_senior <= senior


def test_zero_income_is_zero_tax() -> None:
    for regime in ("new", "old"):
        assert _result(0, regime).total_tax == ZERO


def test_rebate_ceiling_is_exactly_nil() -> None:
    """The single most important boundary in the FY 2026-27 new regime."""
    assert _result(1_200_000).total_tax == ZERO
    assert _result(1_200_010).total_tax > ZERO
