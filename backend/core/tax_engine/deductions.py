"""Chapter VI-A deductions — CORE-006.

Four v1 defects fixed here, all of them overstatements that would have had
users claim deductions they are not entitled to:

  80D      modelled as a flat ₹1,50,000. It is actually a four-way matrix:
           ₹25,000 self/family (₹50,000 if senior) plus ₹25,000 parents
           (₹50,000 if senior), capped at ₹1,00,000 overall. The ₹1,50,000
           figure exists nowhere in the section.

  80CCD    modelled as a separate ₹1,50,000. 80CCD(1) sits INSIDE the
           ₹1,50,000 aggregate ceiling of s.80CCE together with 80C and
           80CCC, so v1 double-counted the entire allowance. Only 80CCD(1B)
           (₹50,000) is genuinely additional, and 80CCD(2) — employer
           contribution — is outside Chapter VI-A limits altogether.

  80DDB    modelled at ₹1,00,000 for everyone. That figure applies only where
           the patient is a senior citizen; otherwise it is ₹40,000.

  regime   not modelled at all. Most of Chapter VI-A is unavailable under the
           new regime, so a user who has opted in and claims 80C gets a
           silently wrong answer.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from backend.core.provenance.money import ZERO, Money
from backend.core.provenance.trace import Op, Step
from backend.core.rules.aliases import cite
from backend.core.rules.loader import TaxRuleset


@dataclass(slots=True)
class DeductionClaim:
    """One claimed amount, plus the facts needed to test it."""

    code: str
    amount: Money
    # 80D
    self_is_senior: bool = False
    parents_are_senior: bool = False
    parents_premium: Money = ZERO
    preventive_checkup: Money = ZERO
    # 80DDB / 80U / 80DD
    patient_is_senior: bool = False
    severe_disability: bool = False


@dataclass(slots=True)
class DeductionOutcome:
    allowed: Money
    claimed: Money
    steps: list[Step] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def disallowed(self) -> Money:
        return (self.claimed - self.allowed).clamp_non_negative()


def _rule(rs: TaxRuleset, code: str) -> Mapping[str, Any]:
    return rs.deduction(code)


# ── 80D — the matrix v1 flattened ───────────────────────────────────────────

def compute_80d(
    claim: DeductionClaim,
    rs: TaxRuleset,
) -> DeductionOutcome:
    r = _rule(rs, "80D")
    citation = cite("80D", rs.fy)

    self_cap = Money(
        r["self_family"]["if_senior"] if claim.self_is_senior
        else r["self_family"]["standard"]
    )
    parents_cap = Money(
        r["parents"]["if_senior"] if claim.parents_are_senior
        else r["parents"]["standard"]
    )

    self_premium = claim.amount
    self_allowed = min(self_premium, self_cap)
    parents_allowed = min(claim.parents_premium, parents_cap)

    steps = [
        Step(
            label=f"80D — self, spouse and children (cap {self_cap})",
            op=Op.MIN,
            result=self_allowed,
            operands=(self_premium, self_cap),
            citation=citation,
            note="senior rate applied" if claim.self_is_senior else "",
        )
    ]
    if claim.parents_premium > ZERO:
        steps.append(
            Step(
                label=f"80D — parents (cap {parents_cap})",
                op=Op.MIN,
                result=parents_allowed,
                operands=(claim.parents_premium, parents_cap),
                citation=citation,
                note="parents are senior citizens" if claim.parents_are_senior else "",
            )
        )

    subtotal = self_allowed + parents_allowed
    notes: list[str] = []

    # Preventive check-up sits WITHIN the caps above, not on top of them.
    if claim.preventive_checkup > ZERO:
        checkup_cap = Money(r["preventive_health_checkup"]["limit"])
        headroom = ((self_cap + parents_cap) - subtotal).clamp_non_negative()
        checkup = min(claim.preventive_checkup, checkup_cap, headroom)
        steps.append(
            Step(
                label=f"80D — preventive health check-up (cap {checkup_cap})",
                op=Op.MIN,
                result=checkup,
                operands=(claim.preventive_checkup, checkup_cap, headroom),
                citation=citation,
                note="within the limits above, not additional",
            )
        )
        subtotal = subtotal + checkup

    absolute = Money(r["absolute_maximum"])
    allowed = min(subtotal, absolute)
    if allowed < subtotal:
        steps.append(
            Step(
                label=f"80D — overall ceiling {absolute}",
                op=Op.MIN,
                result=allowed,
                operands=(subtotal, absolute),
                citation=citation,
            )
        )
        notes.append(
            f"₹{absolute.indian_format()} is the maximum under 80D, reached only "
            f"where both you and your parents are senior citizens."
        )

    return DeductionOutcome(
        allowed=allowed,
        claimed=self_premium + claim.parents_premium + claim.preventive_checkup,
        steps=steps,
        notes=notes,
    )


# ── 80C / 80CCC / 80CCD(1) under the shared 80CCE ceiling ───────────────────

def compute_80cce_group(
    claims: Mapping[str, Money],
    rs: TaxRuleset,
) -> DeductionOutcome:
    """80C + 80CCC + 80CCD(1) share ONE ₹1,50,000 ceiling (s.80CCE).

    v1 gave 80C its own ₹1,50,000 and 80CCD another, letting a user claim
    ₹3,00,000 where the statute permits ₹1,50,000.
    """
    ceiling = Money(_rule(rs, "80CCE")["limit"])
    citation = cite("80C", rs.fy)

    members = ("80C", "80CCC", "80CCD_1")
    claimed = ZERO
    steps: list[Step] = []
    for code in members:
        amount = claims.get(code, ZERO)
        if amount > ZERO:
            claimed = claimed + amount
            steps.append(Step(f"  {code}", Op.LITERAL, amount))

    allowed = min(claimed, ceiling)
    steps.append(
        Step(
            label=f"80C + 80CCC + 80CCD(1) — aggregate ceiling {ceiling}",
            op=Op.MIN,
            result=allowed,
            operands=(claimed, ceiling),
            citation=citation,
            note="s.80CCE — one shared limit, not one each",
        )
    )

    notes = []
    if claimed > ceiling:
        notes.append(
            f"You claimed {claimed} across 80C, 80CCC and 80CCD(1). These share "
            f"a single {ceiling} ceiling under s.80CCE, so {claimed - ceiling} "
            f"is not deductible. Consider 80CCD(1B), which is genuinely "
            f"additional up to ₹50,000."
        )

    return DeductionOutcome(allowed=allowed, claimed=claimed, steps=steps, notes=notes)


# ── 80CCD(2) — employer NPS, the new regime's big lever ─────────────────────

def compute_80ccd2(
    employer_contribution: Money,
    salary: Money,
    rs: TaxRuleset,
    regime: str,
    *,
    is_government_employee: bool = False,
) -> DeductionOutcome:
    """One of very few deductions surviving into the new regime.

    14% of salary under the new regime versus 10% under the old — a material
    difference at any real salary, and absent from v1 entirely.
    """
    r = _rule(rs, "80CCD_2")
    if is_government_employee:
        pct = Decimal(r["percent_of_salary_govt_employee"])
    elif regime == "new":
        pct = Decimal(r["percent_of_salary_new_regime"])
    else:
        pct = Decimal(r["percent_of_salary_old_regime"])

    cap = salary * pct
    allowed = min(employer_contribution, cap)
    return DeductionOutcome(
        allowed=allowed,
        claimed=employer_contribution,
        steps=[
            Step(
                label=f"80CCD(2) — employer NPS (cap {pct * 100:.0f}% of salary = {cap})",
                op=Op.MIN,
                result=allowed,
                operands=(employer_contribution, cap),
                citation=cite("80CCD", rs.fy),
                note=f"{regime} regime rate",
            )
        ],
    )


# ── 80DDB / 80U / 80DD — age and severity conditioned ───────────────────────

def compute_80ddb(claim: DeductionClaim, rs: TaxRuleset) -> DeductionOutcome:
    r = _rule(rs, "80DDB")
    cap = Money(r["limit_senior"] if claim.patient_is_senior else r["limit"])
    allowed = min(claim.amount, cap)
    return DeductionOutcome(
        allowed=allowed,
        claimed=claim.amount,
        steps=[
            Step(
                label=f"80DDB — specified diseases (cap {cap})",
                op=Op.MIN,
                result=allowed,
                operands=(claim.amount, cap),
                citation=cite("80DDB", rs.fy),
                note=(
                    "patient is a senior citizen"
                    if claim.patient_is_senior
                    else "₹1,00,000 applies only where the patient is a senior citizen"
                ),
            )
        ],
    )


def compute_disability(code: str, claim: DeductionClaim, rs: TaxRuleset) -> DeductionOutcome:
    """80U (self) and 80DD (dependant) — a flat amount, not a reimbursement."""
    r = _rule(rs, code)
    amount = Money(r["limit_severe"] if claim.severe_disability else r["limit"])
    return DeductionOutcome(
        allowed=amount,
        claimed=amount,
        steps=[
            Step(
                label=f"{code} — {'severe ' if claim.severe_disability else ''}disability",
                op=Op.LITERAL,
                result=amount,
                citation=cite(code, rs.fy),
                note="a fixed deduction, independent of actual expenditure",
            )
        ],
    )


# ── Savings interest: 80TTA and 80TTB are mutually exclusive ────────────────

def compute_interest_deduction(
    savings_interest: Money,
    deposit_interest: Money,
    age: int,
    rs: TaxRuleset,
) -> DeductionOutcome:
    if age >= 60:
        cap = Money(_rule(rs, "80TTB")["limit"])
        total = savings_interest + deposit_interest
        allowed = min(total, cap)
        code, note = "80TTB", "senior citizen — covers all deposit interest, not just savings"
        operands = (total, cap)
    else:
        cap = Money(_rule(rs, "80TTA")["limit"])
        allowed = min(savings_interest, cap)
        code, note = "80TTA", "savings-account interest only; fixed-deposit interest does not qualify"
        operands = (savings_interest, cap)

    return DeductionOutcome(
        allowed=allowed,
        claimed=savings_interest + deposit_interest,
        steps=[
            Step(
                label=f"{code} — interest (cap {cap})",
                op=Op.MIN,
                result=allowed,
                operands=operands,
                citation=cite(code, rs.fy),
                note=note,
            )
        ],
    )


# ── HRA — the three-way minimum ─────────────────────────────────────────────

def hra_city_rate(city: str | None, rs: TaxRuleset) -> tuple[Decimal, bool]:
    """Resolve the third-limb percentage from the rule pack, by city name.

    Returns (rate, is_listed). The city LIST is the thing that changed for
    FY 2026-27 — Bengaluru, Hyderabad, Pune and Ahmedabad joined the four
    original metros, the first change in over four decades. Resolving it from
    the pack rather than from a caller-supplied boolean is what makes that a
    one-line YAML edit instead of a hunt through call sites.
    """
    cfg = rs.deduction("10_13A")
    listed = {str(c).strip().lower() for c in cfg.get("cities_at_50_percent", ())}
    is_listed = city is not None and city.strip().lower() in listed
    rate = Decimal(str(
        cfg["rate_listed_city"] if is_listed else cfg["rate_other"]
    ))
    return rate, is_listed


def compute_hra_exemption(
    basic_salary: Money,
    hra_received: Money,
    rent_paid: Money,
    is_metro: bool | None = None,
    rs: TaxRuleset | None = None,
    *,
    city: str | None = None,
) -> DeductionOutcome:
    """Least of: HRA received; rent less 10% of salary; 50%/40% of salary.

    An exemption under s.10(13A) — Schedule III, Table Sl. No. 11 of the 2025
    Act — not a Chapter VI-A deduction, so it reduces salary income directly
    and is unavailable under the new regime.

    Pass `city` and the rate comes from the rule pack. `is_metro` is retained
    for callers that genuinely only hold a boolean, but it is the weaker input:
    a caller that decided "metro" in 2025 has Bengaluru wrong for FY 2026-27.
    """
    if rs is None:
        raise ValueError("compute_hra_exemption needs a ruleset")

    if city is not None:
        pct, is_listed = hra_city_rate(city, rs)
        where = f"{city} — {'listed city' if is_listed else 'not a listed city'}"
    else:
        pct, is_listed = hra_city_rate(None, rs)
        if is_metro:
            pct = Decimal(str(rs.deduction("10_13A")["rate_listed_city"]))
        where = "metro" if is_metro else "non-metro"
    rent_less_10 = (rent_paid - basic_salary * Decimal("0.10")).clamp_non_negative()
    salary_pct = basic_salary * pct

    allowed = min(hra_received, rent_less_10, salary_pct)
    return DeductionOutcome(
        allowed=allowed,
        claimed=hra_received,
        steps=[
            Step(
                label="HRA exemption — least of three",
                op=Op.MIN,
                result=allowed,
                operands=(hra_received, rent_less_10, salary_pct),
                citation=cite("10(13A)", rs.fy),
                note=(
                    f"HRA received {hra_received}; rent less 10% of salary "
                    f"{rent_less_10}; {int(pct * 100)}% of salary {salary_pct} "
                    f"({where})"
                ),
            )
        ],
        notes=(
            []
            if allowed == hra_received
            else [f"{hra_received - allowed} of the HRA you receive is taxable."]
        ),
    )


# ── regime gate ─────────────────────────────────────────────────────────────

def filter_by_regime(
    claims: Mapping[str, Money],
    rs: TaxRuleset,
    regime: str,
) -> tuple[dict[str, Money], list[str]]:
    """Split claims into those the regime permits and an explanation for the rest.

    Disallowed deductions are reported, never silently dropped — "your ₹1,50,000
    of 80C does nothing under the new regime" is the single most useful thing
    the product can tell a taxpayer who has opted in by default.
    """
    kept: dict[str, Money] = {}
    rejected: list[str] = []
    for code, amount in claims.items():
        if amount <= ZERO:
            continue
        if rs.deduction_allowed_in(code, regime):
            kept[code] = amount
        else:
            rejected.append(
                f"{code} ({amount}) is not available under the "
                f"{rs.regime(regime).get('name', regime)}"
            )
    return kept, rejected
