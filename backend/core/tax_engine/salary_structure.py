"""What a salaried taxpayer can actually change — PLN-006.

Most "tax saving" advice is a list of sections. This is a list of levers, each
priced by recomputing the whole liability both ways — never by multiplying an
amount by a marginal rate. That distinction is not pedantry: employer NPS of
₹2.1 lakh on a ₹15 lakh salary is worth ₹81,900, not the ₹63,000 a 30%
marginal-rate estimate gives, because the deduction drags taxable income into
the s.87A marginal-relief zone. An estimate is wrong precisely where the number
is largest.

The two levers that matter under the new regime
-----------------------------------------------
Almost everything died with the new regime. Two things did not:

**80CCD(2), employer NPS.** Up to 14% of salary under the new regime against
10% under the old — the single largest lever available to anyone who has opted
in, and it is the employer who has to act, not the employee. Restructuring CTC
to route more through employer NPS costs the employer nothing.

**The standard deduction**, at ₹75,000 rather than ₹50,000.

Under the old regime HRA is usually the biggest number, and FY 2026-27 changed
its shape: the 50% city list went from four to eight. But the exemption is the
LEAST of three amounts, and the percentage limb is often not the binding one —
so "your city moved to 50%" is not the same as "your exemption went up". The
optimiser computes the actual limb rather than announcing the rate.

What this refuses to do
-----------------------
Recommend a restructure the employer cannot deliver. A `SalaryStructure` carries
what is actually negotiable; a lever outside those bounds is reported as
unavailable with the reason, not silently included in a headline saving.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from backend.core.provenance.money import ZERO, Money, pct_of
from backend.core.rules.aliases import cite
from backend.core.rules.loader import TaxRuleset, load_ruleset
from backend.core.tax_engine.compute import TaxInput, compute_tax
from backend.core.tax_engine.deductions import hra_city_rate


@dataclass(slots=True)
class SalaryStructure:
    """The taxpayer's actual position, and what the employer will move.

    `employer_will_restructure` defaults to False. A recommendation to reroute
    CTC is worthless where payroll will not do it, and presenting it as a saving
    the person can bank is worse than saying nothing.
    """

    gross_salary: Money = ZERO
    basic_salary: Money = ZERO
    hra_received: Money = ZERO
    rent_paid: Money = ZERO
    city: str | None = None

    employer_nps: Money = ZERO
    age: int = 0
    regime: str = "new"

    # existing old-regime claims, so the optimiser prices the NEXT rupee
    section_80c: Money = ZERO
    section_80d: Money = ZERO
    section_80ccd_1b: Money = ZERO
    home_loan_interest: Money = ZERO

    employer_will_restructure: bool = False
    is_government_employee: bool = False

    def deduction_map(self) -> dict[str, Money]:
        out: dict[str, Money] = {}
        for code, amount in (
            ("80C", self.section_80c),
            ("80D", self.section_80d),
            ("80CCD_1B", self.section_80ccd_1b),
            ("24b", self.home_loan_interest),
            ("80CCD_2", self.employer_nps),
        ):
            if amount > ZERO:
                out[code] = amount
        return out


@dataclass(frozen=True, slots=True)
class Lever:
    name: str
    section: str
    available: bool
    headroom: Money
    saving: Money
    action: str
    reason: str = ""
    needs_employer: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "section": self.section,
            "available": self.available,
            "headroom": self.headroom.to_json(),
            "saving": self.saving.to_json(),
            "action": self.action,
            "reason": self.reason,
            "needs_employer": self.needs_employer,
        }


@dataclass(slots=True)
class StructuringPlan:
    fy: str
    regime: str
    tax_now: Money
    levers: list[Lever]
    notes: list[str] = field(default_factory=list)

    @property
    def total_saving(self) -> Money:
        total = ZERO
        for lever in self.levers:
            if lever.available:
                total = total + lever.saving
        return total

    def summary(self) -> str:
        usable = [x for x in self.levers if x.available and x.saving > ZERO]
        if not usable:
            return (
                f"Your tax under the {self.regime} regime is {self.tax_now} and "
                f"nothing in your salary structure would reduce it further."
            )
        best = max(usable, key=lambda x: x.saving)
        return (
            f"{self.total_saving} is available across {len(usable)} lever(s). "
            f"The largest is {best.name} at {best.saving}."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "fy": self.fy,
            "regime": self.regime,
            "tax_now": self.tax_now.to_json(),
            "total_saving": self.total_saving.to_json(),
            "levers": [x.to_dict() for x in self.levers],
            "summary": self.summary(),
            "notes": self.notes,
            "citations": [
                c.to_dict() for c in (
                    cite("80CCD", self.fy), cite("10(13A)", self.fy),
                    cite("80C", self.fy), cite("80D", self.fy),
                )
            ],
        }


def _tax(structure: SalaryStructure, rs: TaxRuleset, **overrides: Money) -> Money:
    """Recompute the whole liability. The only honest way to price a lever."""
    claims = structure.deduction_map()
    claims.update(overrides)
    exemptions: dict[str, Money] = {}

    if structure.regime == "old" and structure.hra_received > ZERO:
        exemptions["HRA (s.10(13A))"] = _hra_exempt(structure, rs)

    return compute_tax(
        TaxInput(
            fy=rs.fy, regime=structure.regime, age=structure.age,
            salary=structure.gross_salary, deductions=claims,
            exemptions=exemptions,
        ),
        ruleset=rs,
    ).total_tax


def _hra_exempt(structure: SalaryStructure, rs: TaxRuleset) -> Money:
    """The three-limb minimum, computed rather than assumed."""
    rate, _ = hra_city_rate(structure.city, rs)
    basic = structure.basic_salary or structure.gross_salary
    rent_less_10 = (
        structure.rent_paid - pct_of(basic, Decimal("0.10"))
    ).clamp_non_negative()
    return min(structure.hra_received, rent_less_10, pct_of(basic, rate))


def _nps_ceiling(structure: SalaryStructure, rs: TaxRuleset) -> Money:
    cfg = rs.deduction("80CCD_2")
    key = (
        "percent_of_salary_govt_employee" if structure.is_government_employee
        else f"percent_of_salary_{structure.regime}_regime"
    )
    basic = structure.basic_salary or structure.gross_salary
    return pct_of(basic, Decimal(str(cfg[key])))


def optimise_salary(
    structure: SalaryStructure,
    fy: str,
    *,
    ruleset: TaxRuleset | None = None,
) -> StructuringPlan:
    """Price every lever by recomputation, and say which need the employer."""
    rs = ruleset or load_ruleset(fy)
    baseline = _tax(structure, rs)
    levers: list[Lever] = []
    notes: list[str] = []
    is_new = structure.regime == "new"

    # ── employer NPS — the one that survives into the new regime ────────────
    ceiling = _nps_ceiling(structure, rs)
    headroom = (ceiling - structure.employer_nps).clamp_non_negative()
    if headroom > ZERO:
        saving = (
            baseline - _tax(structure, rs, **{"80CCD_2": ceiling})
        ).clamp_non_negative()
        levers.append(Lever(
            name="Employer NPS contribution",
            section="80CCD(2)",
            available=structure.employer_will_restructure,
            headroom=headroom,
            saving=saving if structure.employer_will_restructure else ZERO,
            action=(
                f"Ask payroll to route {headroom} more of your CTC through "
                f"employer NPS. It costs the employer nothing — it is a "
                f"reallocation, not a rise."
            ),
            reason=(
                "" if structure.employer_will_restructure else
                "Your profile says the employer will not restructure CTC, so "
                "this is shown for information rather than counted as a saving."
            ),
            needs_employer=True,
        ))
        if is_new:
            notes.append(
                f"Under the new regime 80CCD(2) runs to 14% of salary against "
                f"10% under the old, and it is close to the only deduction left. "
                f"Your ceiling is {ceiling}."
            )

    # ── everything below is old-regime only ─────────────────────────────────
    old_only = [
        ("80C", "80C", rs.deduction("80C")["limit"], structure.section_80c,
         "ELSS, PPF, life premium or home loan principal"),
        ("80CCD(1B)", "80CCD_1B", rs.deduction("80CCD_1B")["limit"],
         structure.section_80ccd_1b, "an additional NPS contribution of your own"),
    ]
    for label, code, limit, claimed, what in old_only:
        cap = Money(limit)
        room = (cap - claimed).clamp_non_negative()
        if room <= ZERO:
            continue
        if is_new:
            levers.append(Lever(
                name=f"{label} — {what}", section=label, available=False,
                headroom=room, saving=ZERO,
                action="Not available under the new regime.",
                reason=(
                    "This deduction does not exist under the new regime. "
                    "Claiming it would require switching, which the regime "
                    "comparison prices separately."
                ),
            ))
            continue
        saving = (baseline - _tax(structure, rs, **{code: cap})).clamp_non_negative()
        levers.append(Lever(
            name=f"{label} — {what}", section=label, available=True,
            headroom=room, saving=saving,
            action=f"You have {room} of unused {label} headroom.",
        ))

    # ── HRA ─────────────────────────────────────────────────────────────────
    if structure.hra_received > ZERO:
        levers.append(_hra_lever(structure, rs, is_new))

    if is_new:
        notes.append(
            "You are on the new regime, so HRA, 80C, 80D and self-occupied home "
            "loan interest are all unavailable. Whether switching is worth it is "
            "a separate question — the regime comparison answers it with the "
            "exact breakeven rather than a rule of thumb."
        )

    notes.append(
        "Every figure here comes from recomputing your whole liability both "
        "ways, not from multiplying by a marginal rate. Those differ most "
        "exactly where a deduction crosses a rebate or surcharge threshold, "
        "which is where the amounts are largest."
    )
    return StructuringPlan(
        fy=rs.fy, regime=structure.regime, tax_now=baseline,
        levers=sorted(levers, key=lambda x: (not x.available, -x.saving.amount)),
        notes=notes,
    )


def _hra_lever(
    structure: SalaryStructure, rs: TaxRuleset, is_new: bool
) -> Lever:
    """HRA, and the honest version of the eight-city story.

    The exemption is the least of three amounts. A city moving from 40% to 50%
    only helps where the percentage limb is the binding one — so the lever
    reports which limb actually binds rather than announcing the rate change as
    though it were a saving.
    """
    rate, is_listed = hra_city_rate(structure.city, rs)
    basic = structure.basic_salary or structure.gross_salary
    limbs = {
        "HRA actually received": structure.hra_received,
        "rent paid less 10% of salary": (
            structure.rent_paid - pct_of(basic, Decimal("0.10"))
        ).clamp_non_negative(),
        f"{int(rate * 100)}% of salary": pct_of(basic, rate),
    }
    binding = min(limbs, key=lambda k: limbs[k].amount)
    exempt = limbs[binding]

    if is_new:
        return Lever(
            name="House rent allowance", section="10(13A)", available=False,
            headroom=exempt, saving=ZERO,
            action="Not available under the new regime.",
            reason=(
                f"HRA exemption exists only under the old regime. On your "
                f"figures it would be worth {exempt}, bounded by "
                f"{binding} — factor that into the regime comparison."
            ),
        )

    more_rent = (
        limbs[f"{int(rate * 100)}% of salary"]
        - limbs["rent paid less 10% of salary"]
    ).clamp_non_negative()
    return Lever(
        name="House rent allowance", section="10(13A)", available=True,
        headroom=more_rent, saving=ZERO,
        action=(
            f"Your exemption is {exempt}, bounded by {binding}."
            + (
                f" The {int(rate * 100)}% limb is not what constrains you, so a "
                f"higher city percentage would not help — only more rent, or "
                f"more HRA in your structure, would."
                if binding != f"{int(rate * 100)}% of salary" else
                f" The percentage limb is what constrains you, so your city "
                f"being {'on' if is_listed else 'off'} the 50% list is "
                f"decisive here."
            )
        ),
        reason=(
            "" if is_listed or structure.city is None else
            f"{structure.city} is not on the 50% list, so the third limb is "
            f"40% of salary."
        ),
    )


__all__ = [
    "Lever",
    "SalaryStructure",
    "StructuringPlan",
    "optimise_salary",
]
