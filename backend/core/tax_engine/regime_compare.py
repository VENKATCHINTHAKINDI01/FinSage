"""Old versus new regime, with the exact breakeven — PLN-001.

Both sides come from one engine and one rule pack, so the comparison is
internally consistent. v1 computed the two regimes in a different module with
FY 2024-25 slabs and a hard rebate cliff at ₹7,00,001.

The breakeven
-------------
"Which regime is better?" has a more useful answer than a yes or no: **how many
rupees of old-regime deductions it would take to change the answer**. That
number tells someone whether switching is worth an evening's work or whether
the question is settled.

It is computed rather than sampled. The gap between the two regimes moves
monotonically with deductions — every extra rupee of deduction lowers old-regime
tax and leaves the new regime untouched — so a binary search finds the crossing
to the rupee. At high incomes it lands on exactly ₹8,00,000, which is also what
the algebra gives when both regimes are in the 30% band; `test_regime_compare`
derives it by hand as a check on the engine.

Two things the search deliberately refuses to report
-----------------------------------------------------
**A breakeven at zero tax.** Below roughly ₹12.75L of salary the s.87A rebate
already brings new-regime tax to nil. The old regime can *match* nil with enough
deductions but never beat it — at ₹8L, ₹2,50,000 of 80C buys you the same ₹0 you
already had. Reporting that ₹2,50,000 as a "breakeven" would be advice to lock
up two and a half lakh for nothing, so this returns None and says why.

**False precision.** The search resolves to the rupee, but the result is
presented in round hundreds. Nobody's 80C is tuned to the rupee, and s.288B
rounds the underlying tax to ₹10 anyway.

What the numbers actually say
-----------------------------
Under FY 2026-27 the new regime wins for most people by a wide margin. Sweeping
₹15L–₹50L of salary against realistic deduction levels, the old regime wins only
where someone has a home loan and full HRA on top of a maxed 80C. The honest
output for the majority is "stay where you are, here is the arithmetic" — worth
saying plainly rather than burying under a comparison table.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP
from typing import Any

from backend.core.provenance.citation import Citation
from backend.core.provenance.money import ZERO, Money
from backend.core.provenance.trace import Trace
from backend.core.rules.loader import TaxRuleset, load_ruleset
from backend.core.tax_engine.capital_gains import CapitalGainsResult
from backend.core.tax_engine.compute import TaxInput, TaxResult, compute_tax

# Deductions available under the old regime but not the new one. Only these
# move the breakeven — 80CCD(2) survives into both, so adding employer NPS does
# not push anyone toward the old regime.
_OLD_REGIME_ONLY = ("80C", "80D", "80CCD_1B", "24b", "10_13A", "80E", "80G", "80TTA")

# The breakeven is searched to the rupee, then presented in round hundreds.
# See `_to_nearest_hundred` for why the last few rupees are noise.
_SEARCH_PRECISION = Money(1)


@dataclass(slots=True)
class RegimeComparison:
    fy: str
    old: TaxResult
    new: TaxResult
    better: str
    saving: Money
    breakeven_deductions: Money | None
    current_deductions: Money
    headroom_needed: Money | None
    notes: list[str]

    @property
    def is_close(self) -> bool:
        """Within ₹5,000 either way — worth saying so, because a marginal
        difference should not trigger a regime switch with lock-in consequences
        for anyone with business income."""
        return self.saving < Money(5000)

    def summary(self) -> str:
        if self.saving <= ZERO:
            return f"Both regimes cost the same on these figures ({payable(self.new)})."

        line = (
            f"The {self.better} regime is {self.saving} cheaper for you: "
            f"{payable(self.old)} under the old regime versus "
            f"{payable(self.new)} under the new."
        )
        if self.better == "new" and self.headroom_needed is not None:
            line += (
                f" You would need {self.headroom_needed} MORE in old-regime "
                f"deductions before switching became worthwhile."
            )
        return line

    def to_dict(self) -> dict[str, Any]:
        return {
            "fy": self.fy,
            "better_regime": self.better,
            "saving": self.saving.to_json(),
            "is_close": self.is_close,
            "old": {
                "taxable_income": self.old.taxable_income.to_json(),
                "total_tax": payable(self.old).to_json(),
            },
            "new": {
                "taxable_income": self.new.taxable_income.to_json(),
                "total_tax": payable(self.new).to_json(),
            },
            "current_deductions": self.current_deductions.to_json(),
            "breakeven_deductions": (
                self.breakeven_deductions.to_json()
                if self.breakeven_deductions is not None else None
            ),
            "headroom_needed": (
                self.headroom_needed.to_json()
                if self.headroom_needed is not None else None
            ),
            "summary": self.summary(),
            "notes": self.notes,
            "worksheet_old": self.old.trace.render(),
            "worksheet_new": self.new.trace.render(),
            "citations": [c.to_dict() for c in self.citations()],
        }

    def citations(self) -> list[Citation]:
        """Every provision the two worksheets relied on, deduplicated.

        A recommendation to switch regimes is a recommendation to give up
        deductions, and the user is entitled to see which provisions decided
        it. Collected from the traces rather than authored here, so a citation
        can only appear if a step actually used it.
        """
        seen: dict[str, Citation] = {}
        for trace in (self.old.trace, self.new.trace):
            for citation in trace.citations():
                seen.setdefault(citation.display, citation)
        return sorted(seen.values(), key=lambda c: c.display)


def _tax_for(
    regime: str,
    income: Money,
    deductions: dict[str, Money],
    fy: str,
    age: int,
    rs: TaxRuleset,
    is_salary: bool = True,
    gains: CapitalGainsResult | None = None,
) -> TaxResult:
    return compute_tax(
        TaxInput(
            fy=fy, regime=regime, age=age,
            salary=income if is_salary else ZERO,
            other_sources=ZERO if is_salary else income,
            deductions=dict(deductions),
            special_rate_tax=gains.total_tax if gains else ZERO,
            special_rate_income=gains.total_special_rate_income if gains else ZERO,
        ),
        ruleset=rs,
    )


def payable(result: TaxResult) -> Money:
    """What the user actually writes a cheque for.

    `TaxResult` carries both the exact liability and the s.288B figure rounded
    to the nearest ₹10. Every number shown to a user must be the rounded one —
    quoting ₹97,502.08 when the demand will read ₹97,500 is a small error that
    destroys confidence in every other figure on the page.

    The breakeven search deliberately uses the *unrounded* liability instead,
    because rounding turns the comparison into a step function and puts a ₹5
    artefact on an otherwise exact answer.
    """
    return result.total_tax


def breakeven_deductions(
    income: Money,
    fy: str,
    *,
    age: int = 0,
    is_salary: bool = True,
    gains: CapitalGainsResult | None = None,
    ruleset: TaxRuleset | None = None,
) -> Money | None:
    """The old-regime deduction total at which the two regimes cost the same.

    Binary search, because the difference is monotone in deductions: every
    rupee of old-regime deduction lowers old-regime tax and leaves new-regime
    tax untouched. Sampling at round numbers would give "about ₹5 lakh"; this
    gives the actual crossing point.

    Returns None where no achievable deduction total makes the old regime
    strictly cheaper.

    That includes the case most salaried people are in. Below roughly ₹12.75L
    of salary the new regime's s.87A rebate already brings tax to zero, and the
    old regime can at best *match* zero — never beat it. Reporting a breakeven
    there would be actively harmful: it would tell someone to spend ₹2.5 lakh
    on 80C instruments to arrive at the same ₹0 they already have.
    """
    rs = ruleset or load_ruleset(fy)

    # Searched on the *unrounded* liability. s.288B rounding to the nearest ₹10
    # turns the comparison into a step function, which put a spurious ₹5 on an
    # answer that is exactly ₹8,00,000 at high incomes.
    new_result = _tax_for("new", income, {}, fy, age, rs, is_salary, gains)
    new_tax = new_result.total_tax_exact

    if payable(new_result) <= ZERO:
        return None  # nothing to beat; a tie at zero is not a reason to switch

    # Upper bound: deducting the entire salary. If the old regime cannot reach
    # parity even then, it never can.
    ceiling = income
    if _tax_for("old", income, {"80C": ceiling}, fy, age, rs, is_salary, gains).total_tax_exact > new_tax:
        return None

    low, high = ZERO, ceiling
    while (high - low) > _SEARCH_PRECISION:
        mid = Money((low.amount + high.amount) / 2)
        if _tax_for("old", income, {"80C": mid}, fy, age, rs, is_salary, gains).total_tax_exact > new_tax:
            low = mid       # not enough deductions yet
        else:
            high = mid      # the old regime has caught up by here

    return _to_nearest_hundred(high)


def _to_nearest_hundred(value: Money) -> Money:
    """Present the threshold in round hundreds.

    The search resolves to the rupee, but a breakeven quoted as ₹5,43,755
    reads as a guess dressed up as precision. Nobody's 80C is tuned to the
    rupee, and the underlying tax steps in ₹10 anyway.
    """
    hundreds = (value.amount / 100).to_integral_value(rounding=ROUND_HALF_UP)
    return Money(hundreds * 100)


def compare_regimes(
    income: Money | int,
    deductions: dict[str, Money | int] | None = None,
    *,
    fy: str,
    age: int = 0,
    is_salary: bool = True,
    gains: CapitalGainsResult | None = None,
    ruleset: TaxRuleset | None = None,
) -> RegimeComparison:
    """Compute both regimes on identical facts, and the breakeven.

    `is_salary` is not cosmetic. The standard deduction applies only to salary
    and differs between the regimes (₹75,000 new, ₹50,000 old), so classifying
    pension or interest income as salary hands the taxpayer ₹75,000 of relief
    they are not entitled to and tilts the comparison.

    `gains` matters for a reason that is easy to miss. Capital gains are taxed
    at the same special rates in both regimes — s.111A at 20%, s.112A at 12.5%
    — so it is tempting to leave them out of a regime comparison entirely. But
    they count toward total income for surcharge, and surcharge is where the
    two regimes diverge sharply: the old regime goes to 37%, the new one is
    capped at 25%. A taxpayer near ₹2cr with a large gain can have the answer
    decided by surcharge alone, on income that is otherwise regime-neutral.
    """
    rs = ruleset or load_ruleset(fy)
    income = Money(income)
    claims = {k: Money(v) for k, v in (deductions or {}).items()}

    old = _tax_for("old", income, claims, fy, age, rs, is_salary, gains)
    new = _tax_for("new", income, claims, fy, age, rs, is_salary, gains)

    old_payable, new_payable = payable(old), payable(new)
    better = "old" if old_payable < new_payable else "new"
    saving = abs(old_payable - new_payable)

    # Only deductions the old regime uniquely allows move the breakeven.
    current = ZERO
    for code, amount in claims.items():
        if code.upper() in {c.upper() for c in _OLD_REGIME_ONLY}:
            current = current + amount

    threshold = breakeven_deductions(
        income, fy, age=age, is_salary=is_salary, gains=gains, ruleset=rs
    )
    headroom = (
        (threshold - current).clamp_non_negative()
        if threshold is not None and better == "new" else None
    )

    notes: list[str] = []
    if threshold is None and new_payable <= ZERO:
        notes.append(
            "Your tax under the new regime is already nil after the section 87A "
            "rebate. No amount of old-regime deduction can beat zero, so there "
            "is nothing to gain by switching — and nothing to gain from tax-"
            "saving investments made for tax reasons alone."
        )
    elif threshold is None:
        notes.append(
            "At this income the new regime wins regardless of deductions — "
            "there is no amount of old-regime deduction that would overtake it."
        )
    if saving <= ZERO:
        notes.append(
            "Both regimes cost exactly the same here. The new regime is the "
            "better default at a tie: no deduction proofs to maintain, and no "
            "opt-in to reverse later."
        )
    if better == "old":
        notes.append(
            "Switching regimes is not freely reversible every year if you have "
            "business income. Confirm your deductions before opting in."
        )
    if saving > ZERO and saving < Money(5000):
        notes.append(
            "The difference is small. A marginal saving is rarely worth a "
            "regime switch, especially given the lock-in for business income."
        )
    if any(k.upper() == "80CCD_2" for k in claims):
        notes.append(
            "Employer NPS under 80CCD(2) is available in BOTH regimes, so it "
            "does not favour one over the other — but it is worth maximising "
            "either way."
        )

    return RegimeComparison(
        fy=rs.fy, old=old, new=new, better=better, saving=saving,
        breakeven_deductions=threshold, current_deductions=current,
        headroom_needed=headroom, notes=notes,
    )


def comparison_trace(comparison: RegimeComparison) -> Trace:
    """A single worksheet showing both sides and the conclusion."""
    trace = Trace(f"Regime comparison — FY {comparison.fy}")
    old_payable = payable(comparison.old)
    new_payable = payable(comparison.new)
    trace.literal("Tax payable under the old regime", old_payable)
    trace.literal("Tax payable under the new regime", new_payable)
    trace.subtract(
        f"Saving by choosing the {comparison.better} regime",
        max(old_payable, new_payable),
        min(old_payable, new_payable),
    )
    if comparison.breakeven_deductions is not None:
        trace.literal(
            "Old-regime deductions needed to break even",
            comparison.breakeven_deductions,
            note="computed exactly, not estimated",
        )
    return trace
