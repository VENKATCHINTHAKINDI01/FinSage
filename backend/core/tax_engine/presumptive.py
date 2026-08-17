"""Presumptive taxation — CORE-008.

Three schemes, three different shapes, and the differences are where the money
is:

    44AD    small business      6% of digital receipts, 8% of the rest
    44ADA   specified profession 50% of gross receipts, flat
    44AE    goods carriages     a rate per VEHICLE per MONTH, not a percentage

The digital-receipt uplift most tooling misses
-----------------------------------------------
The 44AD turnover ceiling is ₹2 crore, but it rises to ₹3 crore where at least
95% of receipts are non-cash. Same for 44ADA: ₹50 lakh, or ₹75 lakh on the same
condition. A taxpayer at ₹2.4 crore turnover who banks everything is eligible
and will be told they are not by any engine carrying the lower figure alone.

The two rates within 44AD are the same idea applied to income rather than
eligibility: 6% on the digitally-received portion, 8% on the cash portion. Not
6% on everything because most receipts were digital — the split is per rupee.

Lock-in is a five-year consequence of one year's choice
-------------------------------------------------------
Declaring below the presumptive rate under 44AD, having once opted in, locks
you out of the scheme for the FIVE FOLLOWING years and pushes you into books and
audit. It is the single most expensive thing a small business can do casually,
and it has no equivalent under 44ADA or 44AE.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any

from backend.core.provenance.money import ZERO, Money, pct_of
from backend.core.provenance.trace import Trace
from backend.core.rules.aliases import cite
from backend.core.rules.loader import RuleError, TaxRuleset, load_ruleset


class Scheme(str, Enum):
    S44AD = "44AD"
    S44ADA = "44ADA"
    S44AE = "44AE"


@dataclass(frozen=True, slots=True)
class Vehicle:
    """One goods carriage, for 44AE.

    `months_held` counts a part month as a whole one, so a lorry bought on
    28 March contributes a full month.
    """

    gross_weight_kg: int
    months_held: int = 12
    description: str = ""


@dataclass(slots=True)
class PresumptiveResult:
    scheme: Scheme
    fy: str
    eligible: bool
    presumptive_income: Money
    turnover: Money
    reason: str
    trace: Trace
    notes: list[str] = field(default_factory=list)

    @property
    def effective_rate(self) -> str:
        if self.turnover <= ZERO:
            return "0.00%"
        return f"{(self.presumptive_income.amount / self.turnover.amount * 100):.2f}%"

    def to_dict(self) -> dict[str, Any]:
        return {
            "scheme": self.scheme.value,
            "fy": self.fy,
            "eligible": self.eligible,
            "presumptive_income": self.presumptive_income.to_json(),
            "turnover": self.turnover.to_json(),
            "effective_rate": self.effective_rate,
            "reason": self.reason,
            "notes": self.notes,
            "worksheet": self.trace.render(),
            "citation": cite(self.scheme.value, self.fy).to_dict(),
        }


def _cfg(rs: TaxRuleset, scheme: Scheme) -> dict[str, Any]:
    table = rs.presumptive
    if scheme.value not in table:
        raise RuleError(
            f"FY {rs.fy} has no {scheme.value} configuration. Rules are data — "
            f"add it to the pack rather than special-casing here."
        )
    return dict(table[scheme.value])


def _limit_for(cfg: dict[str, Any], digital_share: Decimal, keys: tuple[str, str]) -> Money:
    """The ceiling, uplifted where receipts are overwhelmingly non-cash."""
    plain, digital = keys
    threshold = Decimal(str(cfg["digital_receipts_threshold"]))
    return Money(cfg[digital] if digital_share >= threshold else cfg[plain])


def compute_44ad(
    turnover: Money | int,
    fy: str,
    *,
    digital_receipts: Money | int = 0,
    declared_income: Money | int | None = None,
    ruleset: TaxRuleset | None = None,
) -> PresumptiveResult:
    """6% on digital receipts, 8% on the rest — split per rupee."""
    rs = ruleset or load_ruleset(fy)
    cfg = _cfg(rs, Scheme.S44AD)
    turnover = Money(turnover)
    digital = min(Money(digital_receipts), turnover)
    cash = turnover - digital
    share = (
        digital.amount / turnover.amount if turnover > ZERO else Decimal(0)
    )

    trace = Trace(f"Presumptive income under s.44AD — FY {rs.fy}")
    trace.literal("Gross turnover", turnover)

    limit = _limit_for(cfg, share, ("turnover_limit", "turnover_limit_digital"))
    notes: list[str] = []
    if turnover > limit:
        reason = (
            f"Turnover of {turnover} exceeds the {limit} ceiling for s.44AD "
            f"at your receipt mix, so the scheme is unavailable."
        )
        if share < Decimal(str(cfg["digital_receipts_threshold"])):
            uplifted = Money(cfg["turnover_limit_digital"])
            if turnover <= uplifted:
                notes.append(
                    f"Had at least "
                    f"{Decimal(str(cfg['digital_receipts_threshold'])) * 100:.0f}% "
                    f"of your receipts been non-cash, the ceiling would have "
                    f"been {uplifted} and you would still qualify. That is a "
                    f"banking decision, not a tax one."
                )
        return PresumptiveResult(
            Scheme.S44AD, rs.fy, False, ZERO, turnover, reason, trace, notes,
        )

    rate_digital = Decimal(str(cfg["rate_digital"]))
    rate_cash = Decimal(str(cfg["rate_cash"]))
    citation = cite("44AD", rs.fy)

    income = ZERO
    if digital > ZERO:
        income = income + trace.multiply(
            f"Digital receipts at {rate_digital * 100:.0f}%", digital,
            rate_digital, citation=citation,
        )
    if cash > ZERO:
        income = income + trace.multiply(
            f"Cash receipts at {rate_cash * 100:.0f}%", cash, rate_cash,
            citation=citation,
        )
    if digital > ZERO and cash > ZERO:
        trace.sum_of("Presumptive income", pct_of(digital, rate_digital),
                     pct_of(cash, rate_cash))

    notes.append(
        f"The two rates apply per rupee, not to the whole turnover. Moving "
        f"receipts from cash to bank lowers the rate on those rupees from "
        f"{rate_cash * 100:.0f}% to {rate_digital * 100:.0f}%."
    )
    _lock_in_note(cfg, rs, declared_income, income, notes)

    return PresumptiveResult(
        Scheme.S44AD, rs.fy, True, income, turnover,
        f"Eligible: turnover {turnover} is within the {limit} ceiling.",
        trace, notes,
    )


def _lock_in_note(
    cfg: dict[str, Any],
    rs: TaxRuleset,
    declared: Money | int | None,
    presumptive: Money,
    notes: list[str],
) -> None:
    """The five-year consequence, stated before it is incurred."""
    years = int(rs.presumptive.get("opt_out_lock_in", {}).get("44AD", 0))
    if not years:
        return
    if declared is not None and Money(declared) < presumptive:
        notes.append(
            f"You are declaring {Money(declared)} against a presumptive "
            f"{presumptive}. Declaring BELOW the presumptive rate takes you out "
            f"of s.44AD for the {years} FOLLOWING years, and requires books and "
            f"a tax audit if your income exceeds the basic exemption. This is "
            f"the most expensive thing a small business can do casually."
        )
    else:
        notes.append(
            f"Once you opt in, declaring below the presumptive rate in a later "
            f"year locks you out of s.44AD for the {years} years after it."
        )


def compute_44ada(
    gross_receipts: Money | int,
    fy: str,
    *,
    digital_receipts: Money | int = 0,
    ruleset: TaxRuleset | None = None,
) -> PresumptiveResult:
    """A flat 50% of gross receipts, subject to the ceiling."""
    rs = ruleset or load_ruleset(fy)
    cfg = _cfg(rs, Scheme.S44ADA)
    receipts = Money(gross_receipts)
    digital = min(Money(digital_receipts), receipts)
    share = digital.amount / receipts.amount if receipts > ZERO else Decimal(0)

    trace = Trace(f"Presumptive income under s.44ADA — FY {rs.fy}")
    trace.literal("Gross receipts", receipts)

    limit = _limit_for(
        cfg, share, ("gross_receipts_limit", "gross_receipts_limit_digital")
    )
    if receipts > limit:
        return PresumptiveResult(
            Scheme.S44ADA, rs.fy, False, ZERO, receipts,
            f"Gross receipts of {receipts} exceed the {limit} ceiling for "
            f"s.44ADA at your receipt mix.",
            trace,
        )

    rate = Decimal(str(cfg["rate"]))
    income = trace.multiply(
        f"Presumptive income at {rate * 100:.0f}% of gross receipts",
        receipts, rate, citation=cite("44ADA", rs.fy),
    )
    return PresumptiveResult(
        Scheme.S44ADA, rs.fy, True, income, receipts,
        f"Eligible: gross receipts {receipts} are within the {limit} ceiling.",
        trace,
        notes=[
            "s.44ADA has no opt-out lock-in — unlike s.44AD, leaving the "
            "scheme in one year does not bar you from it the next."
        ],
    )


def compute_44ae(
    vehicles: list[Vehicle],
    fy: str,
    *,
    ruleset: TaxRuleset | None = None,
) -> PresumptiveResult:
    """A rate per vehicle per month — not a percentage of anything.

    Heavy goods vehicles are charged per TONNE of gross weight; everything else
    is a flat monthly figure. So a 25-tonne lorry is ₹25,000 a month and a
    6-tonne one is ₹7,500.
    """
    rs = ruleset or load_ruleset(fy)
    cfg = _cfg(rs, Scheme.S44AE)
    trace = Trace(f"Presumptive income under s.44AE — FY {rs.fy}")

    max_vehicles = int(cfg["max_vehicles"])
    if len(vehicles) > max_vehicles:
        return PresumptiveResult(
            Scheme.S44AE, rs.fy, False, ZERO, ZERO,
            f"You held {len(vehicles)} goods carriages. Owning more than "
            f"{max_vehicles} AT ANY POINT in the year removes eligibility for "
            f"the whole year — it is not a pro-rata test.",
            trace,
        )
    if not vehicles:
        return PresumptiveResult(
            Scheme.S44AE, rs.fy, False, ZERO, ZERO,
            "s.44AE applies to the business of plying, hiring or leasing goods "
            "carriages, and no vehicles were supplied.",
            trace,
        )

    heavy_kg = int(cfg["heavy_goods_vehicle_kg"])
    per_tonne = Money(cfg["rate_per_tonne_per_month_hgv"])
    per_vehicle = Money(cfg["rate_per_vehicle_per_month_other"])
    citation = cite("44AE", rs.fy)

    parts: list[Money] = []
    for i, v in enumerate(vehicles, 1):
        name = v.description or f"vehicle {i}"
        months = max(0, min(12, v.months_held))
        if v.gross_weight_kg > heavy_kg:
            tonnes = Decimal(v.gross_weight_kg) / Decimal(1000)
            amount = per_tonne * tonnes * months
            label = (
                f"{name} — heavy goods vehicle, {tonnes} t x {months} month(s) "
                f"at {per_tonne}/tonne"
            )
        else:
            amount = per_vehicle * months
            label = f"{name} — {months} month(s) at {per_vehicle}"
        parts.append(trace.literal(label, amount, citation=citation))

    income = trace.sum_of("Presumptive income", *parts) if len(parts) > 1 else parts[0]
    return PresumptiveResult(
        Scheme.S44AE, rs.fy, True, income, ZERO,
        f"Eligible: {len(vehicles)} goods carriage(s), within the "
        f"{max_vehicles} limit.",
        trace,
        notes=[
            "A part month counts as a whole one, so a vehicle bought on "
            "28 March contributes a full month.",
            f"Heavy goods vehicle means gross weight over {heavy_kg:,} kg, the "
            f"Motor Vehicles Act definition. Sources conflict on this figure — "
            f"confirm for a vehicle near the boundary.",
        ],
    )


def uses_single_advance_tax_instalment(scheme: Scheme | None) -> bool:
    """The link to PLN-002. Any presumptive scheme pays in one instalment."""
    return scheme is not None


__all__ = [
    "PresumptiveResult",
    "Scheme",
    "Vehicle",
    "compute_44ad",
    "compute_44ada",
    "compute_44ae",
    "uses_single_advance_tax_instalment",
]
