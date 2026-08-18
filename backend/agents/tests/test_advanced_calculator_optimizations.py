"""AdvancedCalculatorAgent._suggest_optimizations — AGT-001.

Every suggestion here used to carry a fabricated figure: a flat rate
(`headroom * 0.20`) or an outright hardcoded guess (80D was "₹30,000
savings, ₹150,000 max limit" — 150,000 is 80C's limit, copy-pasted). Every
suggestion is now `TaxCalculationEngine.calculate_deduction_benefit`'s real
before/after recomputation.
"""

from __future__ import annotations

from backend.agents.advanced_calculator import AdvancedCalculatorAgent
from backend.tools.calculation import TaxCalculationEngine

TAX_DATA = {
    "financial_year": "2026-27",
    "deduction_limits": {"80C": {"limit": 150000}},
}


def _agent() -> AdvancedCalculatorAgent:
    return AdvancedCalculatorAgent.__new__(AdvancedCalculatorAgent)


def test_80c_savings_matches_the_real_deterministic_benefit():
    result = _agent()._suggest_optimizations(
        gross_income=1200000, current_deductions=0, tax_liability=0,
        user_context={}, tax_data=TAX_DATA, taxable_income=1200000,
    )
    strategy = next(s for s in result if "80C" in s["strategy"])
    expected = TaxCalculationEngine.calculate_deduction_benefit(
        deduction_amount=150000, current_taxable_income=1200000, fy="2026-27", regime="old",
    )
    assert strategy["savings"] == float(expected["tax_savings"])


def test_80d_uses_the_real_twenty_five_thousand_limit_not_the_copy_pasted_150000():
    result = _agent()._suggest_optimizations(
        gross_income=1200000, current_deductions=0, tax_liability=0,
        user_context={}, tax_data=TAX_DATA, taxable_income=1200000,
    )
    strategy = next(s for s in result if "80D" in s["strategy"])
    assert "25,000" in strategy["action"]
    assert "150,000" not in strategy["action"]


def test_no_taxable_income_means_no_fabricated_savings():
    result = _agent()._suggest_optimizations(
        gross_income=0, current_deductions=0, tax_liability=0,
        user_context={}, tax_data=TAX_DATA, taxable_income=0,
    )
    for strategy in result:
        assert not strategy.get("savings"), strategy


def test_loss_carry_forward_asserts_no_rupee_figure():
    result = _agent()._suggest_optimizations(
        gross_income=1200000, current_deductions=0, tax_liability=0,
        user_context={"losses": {"capital": 50000}}, tax_data=TAX_DATA,
        taxable_income=1200000,
    )
    strategy = next(s for s in result if "loss carry forward" in s["strategy"].lower())
    assert strategy["savings"] is None


def test_education_loan_interest_is_the_real_user_stated_figure_not_a_flat_rate():
    result = _agent()._suggest_optimizations(
        gross_income=1200000, current_deductions=0, tax_liability=0,
        user_context={"education_loan": 40000}, tax_data=TAX_DATA, taxable_income=1200000,
    )
    strategy = next(s for s in result if "80E" in s["strategy"])
    expected = TaxCalculationEngine.calculate_deduction_benefit(
        deduction_amount=40000, current_taxable_income=1200000, fy="2026-27", regime="old",
    )
    assert strategy["savings"] == float(expected["tax_savings"])
    assert strategy["savings"] != 40000 * 0.20  # the old flat-rate formula
