"""Section 87A rebate with marginal relief — CORE-004.

This is the fix for the single worst defect in v1: the rebate did not exist
anywhere in the engine. A salaried person with ₹11,00,000 taxable income owes
nothing; v1 told them roughly ₹75,000. Every user under ₹12L got a wrong answer.

Mechanics for FY 2026-27, new regime
------------------------------------
Taxable income up to ₹12,00,000 → rebate up to ₹60,000, which cancels the tax
entirely. With the ₹75,000 standard deduction that is ₹12,75,000 of gross salary.

Just above the threshold, marginal relief caps the tax at the excess over
₹12,00,000, so the extra tax can never exceed the extra income:

    taxable ₹12,10,000
    tax on slabs        20,000 (4–8L @5%) + 40,000 (8–12L @10%) + 1,500 (@15%)
                      = ₹61,500
    excess over 12L     ₹10,000
    61,500 > 10,000  →  relief ₹51,500,  tax payable ₹10,000  (+ cess)

Relief runs out where tax equals the excess: 60,000 + 0.15E = E, i.e. at about
₹12,70,588 of taxable income.

Two details that are easy to get wrong, and which the golden corpus pins:
  * relief is computed on tax BEFORE cess; cess then applies to the relieved figure
  * the rebate does not apply against special-rate income (111A / 112A)
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from backend.core.provenance.money import ZERO, Money
from backend.core.provenance.trace import Op, Step
from backend.core.rules.aliases import cite
from backend.core.rules.loader import TaxRuleset


def apply_rebate_87a(
    tax_on_normal_income: Money,
    taxable_income: Money,
    ruleset: TaxRuleset,
    regime: str,
    *,
    tax_on_special_income: Money = ZERO,
) -> tuple[Money, list[Step]]:
    """Return (rebate, steps).

    `tax_on_normal_income` excludes capital gains taxed at special rates —
    the rebate cannot be set against those. `tax_on_special_income` is passed
    only so the worksheet can say so explicitly rather than silently omitting it.
    """
    rule: Mapping[str, Any] = ruleset.regime(regime)["rebate_87a"]
    threshold = Money(rule["max_taxable_income"])
    max_rebate = Money(rule["max_rebate"])
    citation = cite("87A", ruleset.fy)
    steps: list[Step] = []

    if tax_on_special_income > ZERO and rule.get("excludes_special_rate_income", True):
        excluded = ", ".join(rule.get("excluded_sections", ())) or "special rates"
        steps.append(
            Step(
                label="Rebate not available against special-rate income",
                op=Op.LITERAL,
                result=ZERO,
                note=f"{tax_on_special_income} taxed under {excluded}",
                citation=citation,
            )
        )

    # ── full rebate ─────────────────────────────────────────────────────────
    if taxable_income <= threshold:
        rebate = min(tax_on_normal_income, max_rebate)
        steps.append(
            Step(
                label=f"Rebate u/s 87A (income ≤ {threshold})",
                op=Op.MIN,
                result=rebate,
                operands=(tax_on_normal_income, max_rebate),
                citation=citation,
                note=f"capped at {max_rebate}",
            )
        )
        return rebate, steps

    # ── marginal relief ─────────────────────────────────────────────────────
    if not rule.get("marginal_relief", False):
        return ZERO, steps

    excess = taxable_income - threshold
    if tax_on_normal_income <= excess:
        # Past the crossover — ordinary tax is already lower than the relief
        # floor, so no relief is due.
        return ZERO, steps

    relief = tax_on_normal_income - excess
    steps.append(
        Step(
            label="Marginal relief u/s 87A",
            op=Op.SUBTRACT,
            result=relief,
            operands=(tax_on_normal_income, excess),
            citation=citation,
            note=(
                f"income exceeds {threshold} by {excess}; tax is capped at that "
                f"excess so extra tax never exceeds extra income"
            ),
        )
    )
    return relief, steps


def rebate_ceiling(ruleset: TaxRuleset, regime: str) -> Money:
    """Taxable income at or below which tax is nil."""
    return Money(ruleset.regime(regime)["rebate_87a"]["max_taxable_income"])


def tax_free_gross_salary(ruleset: TaxRuleset, regime: str) -> Money:
    """The headline "₹12.75 lakh is tax-free" figure, derived rather than
    hardcoded so it stays correct when either component changes."""
    r = ruleset.regime(regime)
    return Money(r["rebate_87a"]["max_taxable_income"]) + Money(
        r.get("standard_deduction_salary", 0)
    )
