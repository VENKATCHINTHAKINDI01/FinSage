"""Top-level tax computation — the function everything else calls.

Order of operations matters and is easy to get subtly wrong. This is the
sequence the engine follows, and the golden corpus pins every step of it:

    1. gross total income
    2. less deductions (regime-filtered)      → taxable income
    3. slab tax on ordinary income
    4. plus special-rate tax (111A / 112A / 112) — never slab-taxed
    5. less s.87A rebate, with marginal relief  (ordinary income only)
    6. plus surcharge, with marginal relief at every threshold
    7. plus 4% cess on (tax + surcharge)
    8. statutory rounding to the nearest ₹10   (legacy s.288B)

Every stage appends to a replayable `Trace`. Confidence is composed alongside
it from the provenance of the inputs — not authored, and not a constant.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from backend.core.provenance.confidence import Confidence, Provenance
from backend.core.provenance.money import ZERO, Money, format_rate
from backend.core.provenance.trace import Op, Step, Trace
from backend.core.rules.loader import TaxRuleset, load_ruleset
from backend.core.tax_engine.rebate import apply_rebate_87a
from backend.core.tax_engine.slabs import compute_slab_tax, marginal_rate
from backend.core.tax_engine.surcharge import compute_cess, compute_surcharge


@dataclass(slots=True)
class TaxInput:
    """Everything the computation needs, with where each value came from.

    `fy` and `regime` are mandatory. There is no "current year" default:
    revised returns and ITR-U (a 48-month window) need prior years to remain
    computable, and an implicit year is how v1 kept silently computing
    FY 2023-24 tax two years on.
    """

    fy: str
    regime: str = "new"
    age: int = 0

    salary: Money = ZERO
    house_property: Money = ZERO
    business: Money = ZERO
    other_sources: Money = ZERO

    # Special-rate income, taxed outside the slabs entirely.
    special_rate_tax: Money = ZERO
    special_rate_income: Money = ZERO

    deductions: dict[str, Money] = field(default_factory=dict)
    exemptions: dict[str, Money] = field(default_factory=dict)

    taxes_paid: Money = ZERO

    provenance: dict[str, Provenance] = field(default_factory=dict)
    assumptions: dict[str, str] = field(default_factory=dict)
    as_of: date | None = None

    def source_of(self, field_name: str) -> Provenance:
        return self.provenance.get(field_name, Provenance.USER_STATED)


@dataclass(slots=True)
class TaxResult:
    """The answer, its worksheet, and how much to trust the inputs."""

    fy: str
    regime: str
    gross_total_income: Money
    total_deductions: Money
    taxable_income: Money
    tax_on_slabs: Money
    special_rate_tax: Money
    rebate_87a: Money
    tax_after_rebate: Money
    surcharge: Money
    # Liability before cess. Exposed because this — not the final total — is
    # what marginal relief actually bounds, and therefore what the property
    # invariants must be written against. See `pre_cess_liability` below.
    pre_cess_liability: Money
    cess: Money
    total_tax: Money
    total_tax_rounded: Money
    taxes_paid: Money
    balance_payable: Money
    refund_due: Money
    effective_rate: str
    marginal_rate: str
    trace: Trace
    confidence: Confidence

    def to_dict(self) -> dict[str, Any]:
        return {
            "fy": self.fy,
            "regime": self.regime,
            "gross_total_income": self.gross_total_income.to_json(),
            "total_deductions": self.total_deductions.to_json(),
            "taxable_income": self.taxable_income.to_json(),
            "tax_on_slabs": self.tax_on_slabs.to_json(),
            "special_rate_tax": self.special_rate_tax.to_json(),
            "rebate_87a": self.rebate_87a.to_json(),
            "surcharge": self.surcharge.to_json(),
            "pre_cess_liability": self.pre_cess_liability.to_json(),
            "cess": self.cess.to_json(),
            "total_tax": self.total_tax.to_json(),
            "total_tax_rounded": self.total_tax_rounded.to_json(),
            "balance_payable": self.balance_payable.to_json(),
            "refund_due": self.refund_due.to_json(),
            "effective_rate": self.effective_rate,
            "marginal_rate": self.marginal_rate,
            "trace": self.trace.to_dict(),
            "confidence": self.confidence.to_dict(),
        }


def _pct(part: Money, whole: Money) -> str:
    if whole <= ZERO:
        return "0.00%"
    return f"{(part.amount / whole.amount * 100):.2f}%"


def compute_tax(
    inp: TaxInput,
    *,
    ruleset: TaxRuleset | None = None,
    today: date | None = None,
) -> TaxResult:
    """Compute tax for one taxpayer, one year, one regime."""
    rs = ruleset or load_ruleset(inp.fy)
    today = today or inp.as_of or date.today()
    regime_cfg = rs.regime(inp.regime)

    trace = Trace(
        f"Income tax — FY {rs.fy} (AY {rs.assessment_year}) · "
        f"{regime_cfg.get('name', inp.regime)}"
    )
    conf = Confidence()
    conf.rule_age(rs.fy, rs.verified_on, today)

    # ── 1. gross total income ───────────────────────────────────────────────
    heads = [
        ("Salary", inp.salary, "salary"),
        ("Income from house property", inp.house_property, "house_property"),
        ("Business or profession", inp.business, "business"),
        ("Other sources", inp.other_sources, "other_sources"),
    ]
    present = []
    for label, amount, key in heads:
        if amount != ZERO:
            src = inp.source_of(key)
            trace.literal(label, amount, note=f"source: {src.label}")
            conf.input_from(label.lower(), src)
            present.append(amount)

    if inp.special_rate_income != ZERO:
        trace.literal(
            "Capital gains (taxed at special rates)",
            inp.special_rate_income,
            note="not added to slab income",
        )

    gross = trace.sum_of("Gross total income", *present) if present else ZERO
    if not present:
        trace.literal("Gross total income", ZERO)

    # ── 2. deductions ───────────────────────────────────────────────────────
    allowed: list[Money] = []
    for code, amount in sorted(inp.deductions.items()):
        if amount <= ZERO:
            continue
        if not rs.deduction_allowed_in(code, inp.regime):
            trace.literal(
                f"{code} — not available under this regime",
                ZERO,
                note=f"{amount} claimed, disallowed under {regime_cfg.get('name', inp.regime)}",
            )
            continue
        trace.literal(f"Deduction {code}", amount)
        allowed.append(amount)

    sd = Money(regime_cfg.get("standard_deduction_salary", 0))
    if inp.salary > ZERO and sd > ZERO:
        applied_sd = min(sd, inp.salary)
        trace.literal(
            "Standard deduction (salary)",
            applied_sd,
            note=f"FY {rs.fy}, {regime_cfg.get('name', inp.regime)}",
        )
        allowed.append(applied_sd)

    for name, amount in sorted(inp.exemptions.items()):
        if amount > ZERO:
            trace.literal(f"Exemption {name}", amount)
            allowed.append(amount)

    total_deductions = ZERO
    for a in allowed:
        total_deductions = total_deductions + a

    taxable_raw = (gross - total_deductions).clamp_non_negative()
    trace.subtract("Taxable income", gross, *allowed) if allowed else None
    taxable = taxable_raw.round_288a()
    if taxable != taxable_raw:
        trace.rounded(
            "Taxable income (rounded to nearest ₹10)",
            taxable_raw,
            taxable,
            note="legacy s.288A",
        )

    # ── 3. slab tax ─────────────────────────────────────────────────────────
    slab_tax, slab_step = compute_slab_tax(taxable, rs, inp.regime, inp.age)
    trace.add(slab_step)

    # ── 4. special-rate tax ─────────────────────────────────────────────────
    if inp.special_rate_tax != ZERO:
        trace.literal(
            "Tax on capital gains at special rates",
            inp.special_rate_tax,
            note="111A / 112A / 112 — computed separately",
        )

    tax_before_rebate = slab_tax + inp.special_rate_tax

    # ── 5. rebate ───────────────────────────────────────────────────────────
    rebate, rebate_steps = apply_rebate_87a(
        slab_tax, taxable, rs, inp.regime,
        tax_on_special_income=inp.special_rate_tax,
    )
    for s in rebate_steps:
        trace.add(s)

    tax_after_rebate = (tax_before_rebate - rebate).clamp_non_negative()
    if rebate > ZERO:
        trace.subtract("Tax after rebate", tax_before_rebate, rebate)

    # ── 6. surcharge ────────────────────────────────────────────────────────
    def tax_at(income: Money) -> Money:
        """Tax at an arbitrary income, for the marginal relief comparison.

        A full recomputation, not a scaled estimate — relief compares real
        liabilities and getting this wrong reintroduces the cliff it exists
        to remove.
        """
        t, _ = compute_slab_tax(income, rs, inp.regime, inp.age)
        r, _ = apply_rebate_87a(t, income, rs, inp.regime)
        return (t - r).clamp_non_negative()

    total_income_for_surcharge = taxable + inp.special_rate_income
    surcharge, surcharge_steps = compute_surcharge(
        tax_after_rebate,
        total_income_for_surcharge,
        rs,
        inp.regime,
        tax_at=tax_at,
        special_rate_tax=inp.special_rate_tax,
    )
    for s in surcharge_steps:
        trace.add(s)

    # ── 7. cess ─────────────────────────────────────────────────────────────
    subtotal = tax_after_rebate + surcharge
    if surcharge > ZERO:
        trace.sum_of("Tax plus surcharge", tax_after_rebate, surcharge)

    cess, cess_step = compute_cess(subtotal, rs)
    trace.add(cess_step)

    total_tax = subtotal + cess
    trace.sum_of("Total tax liability", subtotal, cess)

    # ── 8. statutory rounding ───────────────────────────────────────────────
    rounded = total_tax.round_288b()
    if rounded != total_tax:
        trace.rounded(
            "Tax payable (rounded to nearest ₹10)", total_tax, rounded,
            note="legacy s.288B",
        )

    # ── settlement ──────────────────────────────────────────────────────────
    balance = ZERO
    refund = ZERO
    if inp.taxes_paid > ZERO:
        trace.literal("Less: taxes already paid (TDS / advance tax)", inp.taxes_paid)
        diff = rounded - inp.taxes_paid
        if diff >= ZERO:
            balance = diff
            trace.subtract("Balance payable", rounded, inp.taxes_paid)
        else:
            refund = -diff
            trace.add(
                Step("Refund due", Op.SUBTRACT, refund,
                     operands=(inp.taxes_paid, rounded))
            )

    for what, value in sorted(inp.assumptions.items()):
        conf.assumption(what, value)

    return TaxResult(
        fy=rs.fy,
        regime=inp.regime,
        gross_total_income=gross,
        total_deductions=total_deductions,
        taxable_income=taxable,
        tax_on_slabs=slab_tax,
        special_rate_tax=inp.special_rate_tax,
        rebate_87a=rebate,
        tax_after_rebate=tax_after_rebate,
        surcharge=surcharge,
        pre_cess_liability=subtotal,
        cess=cess,
        total_tax=total_tax,
        total_tax_rounded=rounded,
        taxes_paid=inp.taxes_paid,
        balance_payable=balance,
        refund_due=refund,
        effective_rate=_pct(total_tax, gross + inp.special_rate_income),
        marginal_rate=f"{format_rate(marginal_rate(taxable, rs, inp.regime, inp.age))}%",
        trace=trace,
        confidence=conf,
    )


def compute_total_tax(
    gross_income: Money | int,
    fy: str,
    regime: str = "new",
    *,
    age: int = 0,
    deductions: dict[str, Money | int] | None = None,
    is_salary: bool = True,
) -> tuple[Money, Trace]:
    """Thin `(value, trace)` wrapper used by the property invariants.

    Note it takes GROSS income: the standard deduction is applied inside, which
    is what makes the post-tax monotonicity property meaningful.
    """
    inp = TaxInput(
        fy=fy,
        regime=regime,
        age=age,
        salary=Money(gross_income) if is_salary else ZERO,
        business=ZERO if is_salary else Money(gross_income),
        deductions={k: Money(v) for k, v in (deductions or {}).items()},
    )
    result = compute_tax(inp)
    return result.total_tax, result.trace


TaxAt = Callable[[Money], Money]
