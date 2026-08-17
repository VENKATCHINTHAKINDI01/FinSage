"""Buying property — PRC-007.

The one thing here that nobody tells you
-----------------------------------------
If the price on the deed is below the circle rate, BOTH parties are taxed on
the gap, on the same transaction, under two different sections:

    seller   s.50C        the stamp duty value is DEEMED to be the
                          consideration for capital gains. Taxed on money that
                          never reached them.
    buyer    s.56(2)(x)   the excess is income from other sources. Taxed on a
                          gift they did not receive.

It is not one trap with two names. It is two provisions with different
tolerances, and a shortfall can be inside the safe harbour for one party and
outside it for the other on the same sale:

    s.50C         a flat 10% of the consideration
    s.56(2)(x)    ₹50,000 OR 10%, whichever is HIGHER

The floor is what makes them diverge. On a ₹4,00,000 plot, 10% is ₹40,000 and
the buyer's tolerance is the ₹50,000 floor — so a ₹45,000 shortfall taxes the
seller and not the buyer. Reporting a single "circle rate warning" gets that
wrong for one of the two people reading it.

Why the safe harbour was hard to verify, and why that is recorded
------------------------------------------------------------------
The department's own s.50C page is a 2018 snapshot carrying the proviso at
105%. The Finance Act 2020 raised it to 110%. Reading the section page alone —
the obvious, diligent thing to do — encodes a tolerance half the true size and
produces a deemed-income warning on transactions that are perfectly safe. The
reasoning is written into `procurement.yaml` beside the rate rather than left
in a commit message.

Stamp duty is not a table here
-------------------------------
Thirty-odd states, each with women-buyer, urban and first-time-buyer variants,
revised at every state Budget. Road tax already shows what a partial table that
looks national costs. So a rate arrives through the gather layer as an admitted
fact from an official source, or it does not arrive and the line is a named
Gap. `StampDutyNotAvailable` is the type that says which.

What this refuses
------------------
Any opinion on whether a locality will appreciate, whether it is a good time to
buy, or whether the price is fair. Those are market judgements. This computes
statutory consequences and says where its coverage ends.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from backend.core.provenance.money import ZERO, Money
from backend.core.provenance.sourcing import CostLine, SourcedFact
from backend.core.provenance.trace import Trace


class StampDutyNotAvailable(Exception):
    """No admitted stamp duty fact for this state.

    Raised rather than averaged. An averaged stamp duty is wrong for most
    buyers by a percentage of the largest purchase of their life.
    """


@dataclass(slots=True)
class PropertyPurchase:
    state: str
    consideration: Money
    stamp_duty_value: Money           # the circle rate / guidance value
    purchase_date: date
    buyer_is_female: bool = False
    is_under_construction: bool = False
    rera_number: str = ""


@dataclass(frozen=True, slots=True)
class DeemedIncome:
    """One side of the circle-rate trap."""

    party: str                        # "seller" | "buyer"
    section: str
    triggered: bool
    shortfall: Money
    tolerance: Money
    amount: Money                     # what gets taxed, if anything
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "party": self.party,
            "section": self.section,
            "triggered": self.triggered,
            "shortfall": self.shortfall.to_json(),
            "tolerance": self.tolerance.to_json(),
            "amount": self.amount.to_json(),
            "amount_display": str(self.amount),
            "detail": self.detail,
        }


@dataclass(slots=True)
class PropertyPack:
    purchase: PropertyPurchase
    seller_exposure: DeemedIncome
    buyer_exposure: DeemedIncome
    lines: list[CostLine] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    trace: Trace | None = None

    @property
    def either_side_triggered(self) -> bool:
        return self.seller_exposure.triggered or self.buyer_exposure.triggered

    @property
    def only_one_side_triggered(self) -> bool:
        """The case a single combined warning gets wrong for one reader."""
        return self.seller_exposure.triggered != self.buyer_exposure.triggered

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.purchase.state,
            "consideration": self.purchase.consideration.to_json(),
            "stamp_duty_value": self.purchase.stamp_duty_value.to_json(),
            "seller": self.seller_exposure.to_dict(),
            "buyer": self.buyer_exposure.to_dict(),
            "either_side_triggered": self.either_side_triggered,
            "only_one_side_triggered": self.only_one_side_triggered,
            "lines": [x.to_dict() for x in self.lines],
            "gaps": self.gaps,
            "notes": self.notes,
            "worksheet": self.trace.render() if self.trace else None,
        }


# ── the trap ────────────────────────────────────────────────────────────────

def circle_rate_exposure(
    purchase: PropertyPurchase, cfg: dict[str, Any],
) -> tuple[DeemedIncome, DeemedIncome, Trace]:
    """Both sides, computed separately because the tolerances differ."""
    rules = cfg["circle_rate"]
    trace = Trace("Circle-rate shortfall")

    shortfall = trace.subtract(
        "Stamp duty value less consideration",
        purchase.stamp_duty_value, purchase.consideration,
    )
    if shortfall < ZERO:
        shortfall = trace.clamp_zero("Shortfall (floored at nil)", shortfall)

    seller_rules = rules["seller"]
    seller_tolerance = trace.multiply(
        f"s.{seller_rules['legacy_section']} tolerance — "
        f"{Decimal(str(seller_rules['tolerance_rate'])) * 100:.0f}% of "
        f"consideration",
        purchase.consideration, Decimal(str(seller_rules["tolerance_rate"])),
    )

    buyer_rules = rules["buyer"]
    buyer_pct = trace.multiply(
        f"s.{buyer_rules['legacy_section']} — "
        f"{Decimal(str(buyer_rules['tolerance_rate'])) * 100:.0f}% of "
        f"consideration",
        purchase.consideration, Decimal(str(buyer_rules["tolerance_rate"])),
    )
    floor = Money(buyer_rules["tolerance_floor"])
    buyer_tolerance = trace.greater_of(
        f"s.{buyer_rules['legacy_section']} tolerance — the higher of "
        f"{floor} and the percentage",
        buyer_pct, floor,
        note=(
            "The floor is what makes the two limbs diverge on a small "
            "transaction."
        ),
    )

    seller = DeemedIncome(
        party="seller",
        section=seller_rules["legacy_section"],
        triggered=shortfall > seller_tolerance,
        shortfall=shortfall,
        tolerance=seller_tolerance,
        amount=purchase.stamp_duty_value if shortfall > seller_tolerance else ZERO,
        detail=(
            (
                f"The stamp duty value exceeds the price by {shortfall}, more "
                f"than the {seller_tolerance} tolerance. Under s."
                f"{seller_rules['legacy_section']} the seller's capital gains "
                f"are computed on {purchase.stamp_duty_value}, not on "
                f"{purchase.consideration} — tax on money that never reached "
                f"them."
            )
            if shortfall > seller_tolerance else
            (
                f"The shortfall of {shortfall} is within the "
                f"{seller_tolerance} tolerance, so s."
                f"{seller_rules['legacy_section']} does not bite and the "
                f"seller's gains are computed on the actual price."
            )
        ),
    )

    buyer = DeemedIncome(
        party="buyer",
        section=buyer_rules["legacy_section"],
        triggered=shortfall > buyer_tolerance,
        shortfall=shortfall,
        tolerance=buyer_tolerance,
        amount=shortfall if shortfall > buyer_tolerance else ZERO,
        detail=(
            (
                f"The shortfall of {shortfall} exceeds the buyer's tolerance "
                f"of {buyer_tolerance} — the higher of {floor} and the "
                f"percentage. Under s.{buyer_rules['legacy_section']} the "
                f"whole {shortfall} is the buyer's income from other sources, "
                f"taxed at their slab rate. It is a gift they did not receive."
            )
            if shortfall > buyer_tolerance else
            (
                f"The shortfall of {shortfall} is within the buyer's "
                f"tolerance of {buyer_tolerance}, so s."
                f"{buyer_rules['legacy_section']} does not bite."
            )
        ),
    )
    return seller, buyer, trace


def stamp_duty_line(
    purchase: PropertyPurchase, facts: dict[str, SourcedFact],
) -> CostLine:
    """From an admitted fact, or not at all.

    Prefers the women-buyer key where it applies, because several states levy
    a lower rate and defaulting to the general rate overstates the cost for
    roughly half of buyers.
    """
    keys = []
    if purchase.buyer_is_female:
        keys.append(f"stamp_duty.{purchase.state}.female")
    keys.append(f"stamp_duty.{purchase.state}")

    for key in keys:
        fact = facts.get(key)
        if fact is None:
            continue
        rate = Decimal(str(fact.value))
        return CostLine(
            f"Stamp duty — {purchase.state}"
            + (" (women-buyer rate)" if key.endswith(".female") else ""),
            purchase.stamp_duty_value * rate,
            fact,
        )

    raise StampDutyNotAvailable(
        f"no admitted stamp duty rate for {purchase.state!r}. Stamp duty is a "
        f"state levy revised at every state Budget, and an averaged rate is "
        f"wrong for most buyers by a percentage of the largest purchase of "
        f"their life. Gather {keys[-1]!r} from the state registration "
        f"department, or report the line as missing."
    )


def build_pack(
    purchase: PropertyPurchase,
    *,
    cfg: dict[str, Any],
    facts: dict[str, SourcedFact] | None = None,
) -> PropertyPack:
    facts = dict(facts or {})
    seller, buyer, trace = circle_rate_exposure(purchase, cfg)
    lines: list[CostLine] = []
    gaps: list[str] = []
    notes: list[str] = []

    try:
        lines.append(stamp_duty_line(purchase, facts))
    except StampDutyNotAvailable as exc:
        gaps.append(str(exc))

    if purchase.buyer_is_female and not any(
        "women-buyer" in x.label for x in lines
    ):
        notes.append(
            "Several states charge a lower stamp duty rate to a woman buyer. "
            "No such rate has been gathered for this state, so none has been "
            "applied — the figure above, if present, is the general rate and "
            "may be higher than what you will actually pay."
        )

    if purchase.is_under_construction and not purchase.rera_number:
        gaps.append(
            "No RERA registration number was given for an under-construction "
            "property. Registration is mandatory for most projects and the "
            "number can be checked on the state RERA portal. Its absence is "
            "not proof of anything — it is a question to ask before paying."
        )
    elif purchase.rera_number:
        notes.append(
            f"RERA number {purchase.rera_number} recorded. This system has not "
            f"checked it against the state portal; verify it there before "
            f"relying on it."
        )

    return PropertyPack(
        purchase=purchase, seller_exposure=seller, buyer_exposure=buyer,
        lines=lines, gaps=gaps, notes=notes, trace=trace,
    )


__all__ = [
    "DeemedIncome",
    "PropertyPack",
    "PropertyPurchase",
    "StampDutyNotAvailable",
    "build_pack",
    "circle_rate_exposure",
    "stamp_duty_line",
]
