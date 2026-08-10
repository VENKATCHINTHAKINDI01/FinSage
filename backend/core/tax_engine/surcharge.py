"""Surcharge with marginal relief — CORE-005.

v1 computed surcharge as a flat multiplier with no relief, which creates a
cliff at every threshold. At ₹50,00,001 of taxable income the surcharge is 10%
of roughly ₹14 lakh of tax — about ₹1.4 lakh — triggered by a single extra
rupee of income. The taxpayer is materially poorer for earning more.

Marginal relief exists precisely to prevent that. The rule, at each threshold T:

    relief = (tax + surcharge at the actual income)
             − (tax + surcharge at T, at the LOWER band's rate)
             − (income − T)

floored at zero. In effect the additional tax can never exceed the additional
income above the threshold.

Two further wrinkles the rule packs carry:
  * the new regime caps surcharge at 25% (the 37% band is old regime only)
  * surcharge on 111A / 112A / 112 capital gains and on dividends is capped at
    15% regardless of total income
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Any

from backend.core.provenance.money import ZERO, Money, format_rate
from backend.core.provenance.trace import Op, Step
from backend.core.rules.loader import TaxRuleset


def _bands(ruleset: TaxRuleset) -> tuple[Mapping[str, Any], ...]:
    return ruleset.surcharge["bands"]


def applicable_rate(
    total_income: Money,
    ruleset: TaxRuleset,
    regime: str,
) -> tuple[Decimal, Money | None]:
    """(rate, threshold at which it starts). Rate is 0 below the first band."""
    cap = Decimal(ruleset.regime(regime).get("surcharge_cap", "1"))
    rate = Decimal("0")
    threshold: Money | None = None

    for band in _bands(ruleset):
        above = Money(band["above"])
        if total_income > above:
            rate = min(Decimal(band["rate"]), cap)
            threshold = above
        else:
            break
    return rate, threshold


def _previous_rate(threshold: Money, ruleset: TaxRuleset, regime: str) -> Decimal:
    """Surcharge rate applying just below `threshold`."""
    cap = Decimal(ruleset.regime(regime).get("surcharge_cap", "1"))
    rate = Decimal("0")
    for band in _bands(ruleset):
        if Money(band["above"]) >= threshold:
            break
        rate = min(Decimal(band["rate"]), cap)
    return rate


def compute_surcharge(
    tax_before_surcharge: Money,
    total_income: Money,
    ruleset: TaxRuleset,
    regime: str,
    *,
    tax_at: Callable[[Money], Money] | None = None,
    special_rate_tax: Money = ZERO,
) -> tuple[Money, list[Step]]:
    """Return (surcharge after marginal relief, steps).

    `tax_at` recomputes tax at an arbitrary income and is required for marginal
    relief — the relief formula compares against the tax at the threshold, not
    a scaled-down version of the tax at the actual income.
    """
    rate, threshold = applicable_rate(total_income, ruleset, regime)
    steps: list[Step] = []

    if rate == 0 or threshold is None:
        return ZERO, steps

    cap = Decimal(ruleset.regime(regime).get("surcharge_cap", "1"))
    declared = max(Decimal(b["rate"]) for b in _bands(ruleset) if total_income > Money(b["above"]))
    if declared > cap:
        steps.append(
            Step(
                label=f"Surcharge capped at {format_rate(cap)}%",
                op=Op.LITERAL,
                result=ZERO,
                note=(
                    f"{ruleset.regime(regime).get('name', regime)} caps surcharge; "
                    f"the {format_rate(declared)}% band does not apply"
                ),
            )
        )

    # Special-rate income (capital gains, dividends) carries its own cap.
    special_cap = Decimal(ruleset.surcharge.get("special_income_cap", "1"))
    normal_tax = tax_before_surcharge - special_rate_tax

    if special_rate_tax > ZERO and rate > special_cap:
        normal_part = normal_tax * rate
        special_part = special_rate_tax * special_cap
        gross = normal_part + special_part
        steps.append(
            Step(
                label=f"Surcharge on ordinary income @ {format_rate(rate)}%",
                op=Op.MULTIPLY,
                result=normal_part,
                operands=(normal_tax,),
                factor=rate,
            )
        )
        steps.append(
            Step(
                label=f"Surcharge on capital gains @ {format_rate(special_cap)}% (capped)",
                op=Op.MULTIPLY,
                result=special_part,
                operands=(special_rate_tax,),
                factor=special_cap,
                note="111A/112A/112 and dividends are capped at 15%",
            )
        )
    else:
        gross = tax_before_surcharge * rate
        steps.append(
            Step(
                label=f"Surcharge @ {format_rate(rate)}% (income above {threshold})",
                op=Op.MULTIPLY,
                result=gross,
                operands=(tax_before_surcharge,),
                factor=rate,
            )
        )

    if not ruleset.surcharge.get("marginal_relief", True) or tax_at is None:
        return gross, steps

    # ── marginal relief ─────────────────────────────────────────────────────
    prev_rate = _previous_rate(threshold, ruleset, regime)
    tax_at_threshold = tax_at(threshold)
    liability_at_threshold = tax_at_threshold + (tax_at_threshold * prev_rate)
    excess_income = total_income - threshold

    liability_now = tax_before_surcharge + gross
    permitted = liability_at_threshold + excess_income
    relief = (liability_now - permitted).clamp_non_negative()

    if relief > ZERO:
        steps.append(
            Step(
                label="Marginal relief on surcharge",
                op=Op.SUBTRACT,
                result=relief,
                operands=(liability_now, permitted),
                note=(
                    f"income exceeds {threshold} by {excess_income}; total tax is "
                    f"capped so the increase never exceeds the extra income"
                ),
            )
        )
        after = (gross - relief).clamp_non_negative()
        steps.append(
            Step(
                label="Surcharge after marginal relief",
                op=Op.SUBTRACT,
                result=after,
                operands=(gross, relief),
            )
        )
        return after, steps

    return gross, steps


def compute_cess(
    tax_plus_surcharge: Money,
    ruleset: TaxRuleset,
) -> tuple[Money, Step]:
    """Health and Education Cess — 4% on tax plus surcharge, after all relief."""
    rate = ruleset.cess_rate
    amount = tax_plus_surcharge * rate
    return amount, Step(
        label=f"Health & Education Cess @ {format_rate(rate)}%",
        op=Op.MULTIPLY,
        result=amount,
        operands=(tax_plus_surcharge,),
        factor=rate,
        note="on income tax plus surcharge",
    )
