"""Progressive slab computation — CORE-003.

Fixes two v1 defects:

  * The slab table was FY 2023-24 vintage (3L/6L/9L/12L, 30% from ₹12L). The
    current new regime has seven bands with 30% starting at ₹24L, so everyone
    above roughly ₹12L was overtaxed.

  * `calculate_income_tax` switched to a `senior_citizen` table at age >= 60
    — but that table held OLD-regime slabs (5L/10L, 20% top rate) while
    everything around it was new-regime. A 62-year-old on ₹30L was taxed at a
    20% top rate instead of 30%. Age bands now come from the rule pack, and
    the new regime declares `age_bands: false`.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from backend.core.provenance.money import ZERO, Money, format_rate
from backend.core.provenance.trace import Op, Step
from backend.core.rules.aliases import cite
from backend.core.rules.loader import TaxRuleset


def band_label(lower: Money, upper: Money | None, rate: Decimal) -> str:
    pct = format_rate(rate)
    if upper is None:
        return f"above {lower} @ {pct}%"
    return f"{lower} – {upper} @ {pct}%"


def compute_slab_tax(
    taxable_income: Money,
    ruleset: TaxRuleset,
    regime: str,
    age: int = 0,
) -> tuple[Money, Step]:
    """Tax before rebate, surcharge and cess.

    Returns the amount and a SLAB step whose children are the individual bands,
    so the worksheet shows exactly which slab contributed what.
    """
    bands: tuple[Mapping[str, Any], ...] = ruleset.slabs(regime, age)

    income = taxable_income.clamp_non_negative()
    total = ZERO
    steps: list[Step] = []
    lower = ZERO

    for band in bands:
        upper_raw = band["upto"]
        upper = None if upper_raw is None else Money(upper_raw)
        rate = Decimal(band["rate"])

        if upper is not None and income <= lower:
            break

        slice_top = income if upper is None else min(income, upper)
        chargeable = (slice_top - lower).clamp_non_negative()

        if chargeable > ZERO:
            band_tax = chargeable * rate
            total = total + band_tax
            steps.append(
                Step(
                    label=band_label(lower, upper, rate),
                    op=Op.MULTIPLY,
                    result=band_tax,
                    operands=(chargeable,),
                    factor=rate,
                    note=f"on {chargeable}",
                )
            )

        if upper is None:
            break
        lower = upper
        if income <= lower:
            break

    if not steps:
        steps.append(
            Step(
                label="Below the basic exemption limit",
                op=Op.LITERAL,
                result=ZERO,
                note=f"taxable income {income}",
            )
        )

    regime_name = ruleset.regime(regime).get("name", regime)
    age_note = ""
    if ruleset.regime(regime).get("age_bands", False):
        if age >= 80:
            age_note = " · super-senior (80+)"
        elif age >= 60:
            age_note = " · senior (60–79)"

    # The new regime's rates are set by s.115BAC; the old regime's come from
    # the Finance Act rate schedule for the year, which has no Income-tax Act
    # section to point at. Citing 115BAC for the old regime would be worse than
    # citing nothing, so the old regime gets a rule-pack reference instead.
    citation = cite("115BAC", ruleset.fy) if regime == "new" else None

    return total, Step(
        label=f"Tax on slabs — {regime_name}{age_note}",
        op=Op.SLAB,
        result=total,
        children=tuple(steps),
        citation=citation,
        note="" if citation else f"Finance Act rate schedule, FY {ruleset.fy}",
    )


def marginal_rate(
    taxable_income: Money,
    ruleset: TaxRuleset,
    regime: str,
    age: int = 0,
) -> Decimal:
    """The rate applying to the next rupee.

    Used for "what would this deduction save you" style answers. It is a rate,
    not an amount — the amount always comes from a full recomputation, because
    a marginal rate ignores rebate and surcharge boundaries.
    """
    for band in ruleset.slabs(regime, age):
        upper = band["upto"]
        if upper is None or taxable_income < Money(upper):
            return Decimal(band["rate"])
    return Decimal(ruleset.slabs(regime, age)[-1]["rate"])
