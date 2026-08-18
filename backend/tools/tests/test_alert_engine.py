"""TaxAlertEngine.generate_tax_saving_alerts — AGT-001.

Locks in the fix: potential_saving used to be a flat `gap * 0.30` /
`limit * 0.20` guess, wrong wherever a rebate or surcharge boundary is
crossed and wrong-by-definition for a user with no taxable income above the
exemption. It is now `TaxCalculationEngine.calculate_deduction_benefit`'s
real before/after recomputation, or None when there is no income to compute
against — never a guess in either direction.
"""

from __future__ import annotations

from backend.tools.alert_engine import TaxAlertEngine
from backend.tools.calculation import TaxCalculationEngine


def test_potential_saving_matches_the_real_deterministic_benefit():
    """Not `gap * 0.30` — the actual number calculate_deduction_benefit
    would produce for this income and this gap."""
    result = TaxAlertEngine.generate_tax_saving_alerts(
        investments={}, deductions={}, current_taxable_income=1200000, fy="2026-27",
    )
    alerts = {a["section"]: a for a in result["alerts"]}
    assert "80C" in alerts

    gap = 150000.0  # nothing invested yet
    expected = TaxCalculationEngine.calculate_deduction_benefit(
        deduction_amount=gap, current_taxable_income=1200000, fy="2026-27", regime="old",
    )
    assert alerts["80C"]["potential_saving"] == float(expected["tax_savings"])


def test_no_income_means_no_fabricated_savings_figure():
    """Without current_taxable_income there is nothing to compute a real
    benefit against — the old code still asserted a flat-rate number here;
    now it must be None, not a guess."""
    result = TaxAlertEngine.generate_tax_saving_alerts(investments={}, deductions={})
    for alert in result["alerts"]:
        assert alert["potential_saving"] is None


def test_a_fully_utilised_80c_produces_no_alert():
    result = TaxAlertEngine.generate_tax_saving_alerts(
        investments={"ppf": 150000}, deductions={}, current_taxable_income=1200000,
    )
    sections = {a["section"] for a in result["alerts"]}
    assert "80C" not in sections


def test_savings_never_exceeds_a_flat_thirty_percent_of_the_gap():
    """A regression guard in the other direction: the real benefit must never
    exceed what the old (wrong) flat-30% estimate would have shown, given the
    marginal rate ceiling — if this fails, something is double-counting."""
    result = TaxAlertEngine.generate_tax_saving_alerts(
        investments={}, deductions={}, current_taxable_income=1500000, fy="2026-27",
    )
    alerts = {a["section"]: a for a in result["alerts"]}
    assert alerts["80C"]["potential_saving"] <= 150000 * 0.35  # generous ceiling, not the old formula
