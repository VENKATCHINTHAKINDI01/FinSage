"""What a purchase actually costs you — PRC-003.

The gap this closes
-------------------
The number a dealer quotes is not the number that leaves your account, and
neither is the number that leaves your account the cost to you. Three different
figures, and most tooling conflates them:

    ex-showroom      what the price list says
    on-road          plus GST, road tax, registration, insurance
    landed cost      minus subsidies, minus input tax credit, minus the
                     income-tax effect of depreciation

For a GST-registered business buying a commercial vehicle the third can be
lakhs below the second. For a salaried buyer it is usually the same, and saying
so plainly is more useful than implying a benefit that is not there.

Three things this refuses to do
--------------------------------
**Guess a state.** Road tax is a state levy with thirty-odd different schedules.
An unlisted state raises rather than averaging — an averaged road tax is
confidently wrong by tens of thousands of rupees while looking authoritative.

**Grant blocked ITC.** GST credit on a passenger vehicle is BLOCKED under
s.17(5) except for resale, passenger transport, driving instruction or goods
transport. A GST-registered consultancy buying a car gets nothing, and an engine
that grants it overstates the saving by the entire GST amount — the single
largest error available in this whole model.

**Cost from a marketplace listing.** Every line is a `CostLine`, which cannot be
built from a Tier-3 source (PRC-002). The type system carries that, not this
module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from backend.core.provenance.money import ZERO, Money, pct_of
from backend.core.provenance.sourcing import CostLine, SourcedFact, Tier
from backend.core.provenance.trace import Trace
from backend.core.rules.loader import RuleError, TaxRuleset, load_ruleset


class StateNotCovered(RuleError):
    """Road tax was requested for a state with no verified schedule."""


@dataclass(slots=True)
class Purchase:
    """What is being bought, by whom, where and when."""

    item: str
    ex_showroom: Money
    category: str                 # keys gst.rates_by_category
    state: str
    purchase_date: date

    is_electric: bool = False
    insurance: Money = ZERO
    logistics_and_handling: Money = ZERO
    accessories: Money = ZERO

    subsidies: dict[str, Money] = field(default_factory=dict)
    discounts: dict[str, Money] = field(default_factory=dict)

    # business buyer
    is_gst_registered: bool = False
    is_business_use: bool = False
    business_use_kind: str = ""   # keys input_tax_credit.motor_vehicle_blocked_unless
    depreciation_block: str = ""
    marginal_tax_rate: Decimal = Decimal("0.30")
    days_used_in_year: int = 365


@dataclass(slots=True)
class LandedCost:
    purchase: Purchase
    lines: list[CostLine]
    on_road: Money
    landed: Money
    trace: Trace
    notes: list[str] = field(default_factory=list)

    @property
    def total_deductions(self) -> Money:
        out = ZERO
        for line in self.lines:
            if line.is_deduction:
                out = out + line.amount
        return out

    def summary(self) -> str:
        return (
            f"{self.purchase.item}: {self.purchase.ex_showroom} ex-showroom, "
            f"{self.on_road} on the road, {self.landed} once subsidies and tax "
            f"effects are counted."
        )

    def to_dict(self, today: date | None = None) -> dict[str, Any]:
        return {
            "item": self.purchase.item,
            "state": self.purchase.state,
            "purchase_date": self.purchase.purchase_date.isoformat(),
            "ex_showroom": self.purchase.ex_showroom.to_json(),
            "on_road": self.on_road.to_json(),
            "landed_cost": self.landed.to_json(),
            "total_deductions": self.total_deductions.to_json(),
            "lines": [x.to_dict(today) for x in self.lines],
            "summary": self.summary(),
            "notes": self.notes,
            "worksheet": self.trace.render(),
        }


# ── rule lookups ────────────────────────────────────────────────────────────

def _gst_schedule(pack: dict[str, Any], on: date) -> dict[str, Any]:
    """The schedule in force ON THE PURCHASE DATE.

    GST 2.0 restructured everything on 22 September 2025, mid-year. A purchase
    is costed against what applied when it happened, not what applies today.
    """
    applicable = [
        s for s in pack["schedules"]
        if date.fromisoformat(str(s["effective_from"])) <= on
    ]
    if not applicable:
        raise RuleError(f"no GST schedule in force on {on.isoformat()}")
    return max(applicable, key=lambda s: date.fromisoformat(str(s["effective_from"])))


def gst_rate_for(category: str, on: date, pack: dict[str, Any]) -> tuple[Decimal, str]:
    schedule = _gst_schedule(pack, on)
    rates = schedule.get("rates_by_category", {})
    if category in rates:
        return Decimal(str(rates[category])), schedule["name"]
    return Decimal(str(schedule["default_slab"])), schedule["name"]


def road_tax_rate(
    state: str,
    purchase: Purchase,
    cfg: dict[str, Any],
    *,
    facts: dict[str, SourcedFact] | None = None,
) -> Decimal:
    """The state's rate, from a gathered fact first and the pack second.

    Coverage used to end at the four states in `procurement.yaml`, and an
    unlisted state raised. That refusal was right — averaging road tax is wrong
    by tens of thousands of rupees while looking authoritative — but it made
    the table a ceiling on the product rather than a floor.

    A fact admitted through the gather layer (PRC-010/011) now takes
    precedence, so a state arrives by being SOURCED rather than by being typed
    into this repository. The pack remains as the verified baseline for the
    states it covers, and the raise remains for a state with neither. Nothing
    is averaged at any point.

    A gathered fact wins over the pack deliberately: it is dated, it carries
    its URL, and it was re-read more recently than the file. The pack entry is
    a snapshot of the same thing taken by hand.
    """
    facts = facts or {}
    for key in (
        f"road_tax.{state}.ev" if purchase.is_electric else "",
        f"road_tax.{state}",
    ):
        if key and key in facts:
            return Decimal(str(facts[key].value))

    states = cfg["road_tax"]["states"]
    if state not in states:
        raise StateNotCovered(
            f"no road tax rate for {state!r}: it is not among the verified "
            f"states {sorted(states)} and no fact has been gathered for "
            f"'road_tax.{state}'. Road tax is a state levy and averaging it "
            f"produces a landed cost that is wrong by tens of thousands of "
            f"rupees while looking authoritative — so this raises instead. "
            f"Gather the rate from the state transport department."
        )
    entry = states[state]
    if purchase.is_electric:
        return Decimal(str(entry["ev_rate"]))
    for band in entry["petrol_bands"]:
        upper = band["upto"]
        if upper is None or purchase.ex_showroom <= Money(upper):
            return Decimal(str(band["rate"]))
    return Decimal(str(entry["petrol_bands"][-1]["rate"]))


def itc_available(purchase: Purchase, cfg: dict[str, Any]) -> tuple[bool, str]:
    """Whether GST paid can be reclaimed — and why not, when it cannot."""
    rules = cfg["input_tax_credit"]
    if not purchase.is_gst_registered:
        return False, "you are not GST-registered, so there is no credit to claim"
    if not purchase.is_business_use:
        return False, "the asset is for personal use, so no credit arises"

    is_vehicle = "vehicle" in purchase.category or "vehicle" in purchase.depreciation_block
    if is_vehicle:
        allowed = list(rules["motor_vehicle_blocked_unless"])
        if purchase.business_use_kind not in allowed:
            return False, (
                f"GST credit on a passenger vehicle is blocked under s.17(5) "
                f"unless it is used for {', '.join(allowed)}. General business "
                f"use does not qualify, however legitimate."
            )
    return True, ""


# ── the model ───────────────────────────────────────────────────────────────

def compute_landed_cost(
    purchase: Purchase,
    fy: str,
    *,
    facts: dict[str, SourcedFact] | None = None,
    ruleset: TaxRuleset | None = None,
) -> LandedCost:
    """Every line, sourced, in order."""
    # The income-tax ruleset is loaded to validate the year even where no
    # figure is drawn from it — an unknown FY must fail here rather than
    # producing a cost with no tax context.
    load_ruleset(fy) if ruleset is None else ruleset
    gst_pack = _load("gst.yaml")
    proc = _load("procurement.yaml")
    facts = dict(facts or {})

    def fact_for(key: str, url: str, kind: str) -> SourcedFact:
        if key in facts:
            return facts[key]
        return SourcedFact(
            key=key, value="rule pack", source_url=url, tier=Tier.OFFICIAL,
            fetched_on=date.fromisoformat(str(
                (gst_pack if key.startswith("gst") else proc)["meta"]["verified_on"]
            )),
            source_kind=kind,
        )

    trace = Trace(f"Landed cost — {purchase.item}")
    lines: list[CostLine] = []
    notes: list[str] = []

    base = trace.literal("Ex-showroom price", purchase.ex_showroom)
    lines.append(CostLine(
        "Ex-showroom price", purchase.ex_showroom,
        fact_for("price.ex_showroom", "https://oem.example/price-list", "oem_price_list"),
    ))

    # ── GST ─────────────────────────────────────────────────────────────────
    rate, schedule_name = gst_rate_for(purchase.category, purchase.purchase_date, gst_pack)
    gst = trace.multiply(
        f"GST at {rate * 100:.0f}% ({schedule_name})", purchase.ex_showroom, rate,
    )
    lines.append(CostLine(
        f"GST at {rate * 100:.0f}%", gst,
        fact_for("gst." + purchase.category, "https://www.cbic.gov.in/", "gst"),
    ))
    if purchase.is_electric and rate == Decimal("0.05"):
        notes.append(
            "Electric vehicles are at 5% GST against 18% or 40% for the "
            "equivalent petrol model — the largest single line in favour of an "
            "EV, and it is a rate rather than a subsidy, so it does not expire."
        )

    # ── road tax and registration ───────────────────────────────────────────
    rt_rate = road_tax_rate(purchase.state, purchase, proc, facts=facts)
    state_name = (
        proc["road_tax"]["states"].get(purchase.state, {}).get("name")
        or purchase.state
    )
    road_tax = trace.multiply(
        f"Road tax — {state_name} at {rt_rate * 100:.0f}%",
        purchase.ex_showroom, rt_rate,
    )
    lines.append(CostLine(
        "Road tax", road_tax,
        fact_for(f"road_tax.{purchase.state}", "https://parivahan.gov.in/", "road_tax"),
    ))
    if purchase.is_electric and rt_rate == Decimal(0):
        notes.append(
            f"{state_name} charges no "
            f"road tax on a battery electric vehicle. That exemption is a state "
            f"policy with its own window — confirm it still applies on the day "
            f"you register."
        )

    reg = Money(proc["road_tax"]["registration_charge_default"])
    reg_line = trace.literal("Registration and handling", reg)
    lines.append(CostLine(
        "Registration", reg,
        fact_for("registration", "https://parivahan.gov.in/", "road_tax"),
    ))

    extras = ZERO
    for label, amount in (
        ("Insurance", purchase.insurance),
        ("Logistics and handling", purchase.logistics_and_handling),
        ("Accessories", purchase.accessories),
    ):
        if amount > ZERO:
            extras = extras + trace.literal(label, amount)
            lines.append(CostLine(
                label, amount,
                fact_for("quote." + label.lower(), "https://dealer.example/quote",
                         "oem_price_list"),
            ))

    on_road = trace.sum_of(
        "On-road price", base, gst, road_tax, reg_line, *([extras] if extras > ZERO else []),
    )

    # ── what comes back off ─────────────────────────────────────────────────
    running = on_road

    for name, amount in {**purchase.subsidies, **purchase.discounts}.items():
        if amount <= ZERO:
            continue
        running = trace.subtract(f"Less: {name}", running, amount)
        lines.append(CostLine(
            name, amount,
            fact_for("subsidy." + name, "https://heavyindustries.gov.in/",
                     "state_ev_policy"),
            is_deduction=True,
        ))

    available, why_not = itc_available(purchase, proc)
    if available:
        running = trace.subtract("Less: input tax credit on GST", running, gst)
        lines.append(CostLine(
            "Input tax credit", gst,
            fact_for("itc", "https://www.cbic.gov.in/", "gst"), is_deduction=True,
        ))
    elif purchase.is_gst_registered:
        notes.append(f"No input tax credit: {why_not}")

    # ── the income-tax effect ───────────────────────────────────────────────
    if purchase.is_business_use and purchase.depreciation_block:
        dep_saving = _depreciation_effect(purchase, proc, trace, notes)
        if dep_saving > ZERO:
            running = trace.subtract(
                "Less: first-year tax saved through depreciation", running, dep_saving,
            )
            lines.append(CostLine(
                "First-year depreciation tax effect", dep_saving,
                fact_for("depreciation", "https://www.incometaxindia.gov.in/",
                         "gst"),
                is_deduction=True,
            ))

    if not purchase.is_business_use:
        notes.append(
            "There is no income-tax effect here: depreciation and input tax "
            "credit are business reliefs. For a personal purchase the on-road "
            "price is the landed cost."
        )

    return LandedCost(
        purchase=purchase, lines=lines, on_road=on_road, landed=running,
        trace=trace, notes=notes,
    )


def _depreciation_effect(
    purchase: Purchase, proc: dict[str, Any], trace: Trace, notes: list[str]
) -> Money:
    """First-year depreciation, and the tax it saves.

    The half-rate rule is the part with teeth: an asset used for fewer than 180
    days gets half the normal rate in year one. It is why 31 March and 1 April
    are materially different dates for a business buyer.
    """
    cfg = proc["depreciation"]
    rates = cfg["block_rates"]
    block = purchase.depreciation_block
    if block not in rates:
        raise RuleError(
            f"no depreciation rate for block {block!r}; available: {sorted(rates)}"
        )

    rate = Decimal(str(rates[block]))
    threshold = int(cfg["half_rate_if_used_under_days"])
    halved = purchase.days_used_in_year < threshold
    applied = rate / 2 if halved else rate

    dep = trace.multiply(
        f"Depreciation at {applied * 100:.1f}%"
        + (" (half rate — used under 180 days)" if halved else ""),
        purchase.ex_showroom, applied,
    )
    if halved:
        notes.append(
            f"Used for {purchase.days_used_in_year} days, under the "
            f"{threshold}-day threshold, so depreciation is HALF the normal "
            f"{rate * 100:.0f}% this year. The other half is not lost — it "
            f"arrives in later years through the written-down value."
        )
    return pct_of(dep, purchase.marginal_tax_rate)


def _load(name: str) -> dict[str, Any]:
    import pathlib

    import yaml

    from backend.core.rules.loader import RULES_DIR

    path = pathlib.Path(RULES_DIR) / name
    if not path.exists():
        raise RuleError(f"rule pack {name} is missing")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


__all__ = [
    "LandedCost",
    "Purchase",
    "StateNotCovered",
    "compute_landed_cost",
    "gst_rate_for",
    "itc_available",
    "road_tax_rate",
]
