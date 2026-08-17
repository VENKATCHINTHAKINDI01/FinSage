"""What a scheme is actually worth to this buyer — PRC-004.

CORE-009 answered "may I claim this?". It could not answer "how much?", because
`max_benefit` in the rule data is a single scalar and most schemes are not.

    80EEB            flat        ₹1,50,000
    e-2W incentive   per unit    ₹2,500 per kWh, capped at ₹5,000
    PM-KUSUM B       percentage  30% of benchmark or tender cost, lower of
    PM-Surya Ghar    tiered      ₹30,000/kWp on the first 2, ₹18,000 on the 3rd

A scalar forces all four into the first one's shape, and the three that do not
fit get rounded to whatever the largest possible claim is. Quoting a ₹5,000
two-wheeler incentive to someone buying a 1.5 kWh scooter — worth ₹3,750 — is
the same class of error as quoting a closed window: the statute says the
number, and the number is not theirs.

The fifth kind is the one that matters most
--------------------------------------------
`UNVERIFIED`. A scheme that demonstrably exists, whose amount has NOT been
confirmed against a Tier-1 source. It reports as existing, with the amount
named as unconfirmed and the source to check.

The alternative is to write down what a secondary site says the amount is, and
the alternative to that is to record ₹0, which reads as "this scheme is worth
nothing to you" — a false statement dressed as a computed one. There is no
version of this where inventing the number is the honest option, so the type
system carries the distinction: `BenefitAmount.stated` is False and every
renderer has to decide what to do about it.

Every figure is a recomputation
--------------------------------
The same discipline as PLN-006. `Trace` carries the arithmetic, so the ₹3,750
above is a worksheet a user can follow, not an assertion. A capped per-unit
benefit that silently returns the cap is indistinguishable from one that
computed correctly and happened to hit it; the trace tells them apart.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any

from backend.core.provenance.money import ZERO, Money, format_rate
from backend.core.provenance.trace import Trace


class BenefitError(Exception):
    """A benefit block in the rule data is malformed.

    Raised rather than returned. A rule pack that does not parse is a bug in
    the pack, not a fact about the user, and degrading to zero would hide it.
    """


class BenefitKind(str, Enum):
    FLAT = "flat"
    PER_UNIT = "per_unit"
    PERCENTAGE = "percentage"
    SLAB = "slab"
    TIERED = "tiered"
    UNVERIFIED = "unverified"


@dataclass(frozen=True, slots=True)
class BenefitAmount:
    """How much, how it was reached, and whether we stand behind the figure."""

    amount: Money = ZERO
    stated: bool = True
    basis: str = ""
    trace: Trace | None = None
    missing_fields: tuple[str, ...] = ()
    capped: bool = False
    unverified_note: str = ""

    @property
    def computable(self) -> bool:
        return self.stated and not self.missing_fields

    def phrase(self) -> str:
        """How a benefit is named in a sentence, including when it is not
        known. Kept here rather than in the renderer so that every surface
        says the same thing about an unverified amount."""
        if not self.stated:
            return "an amount this system has not verified"
        if self.missing_fields:
            return f"an amount that depends on {', '.join(self.missing_fields)}"
        return f"up to {self.amount}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "amount": self.amount.to_json(),
            "display": str(self.amount) if self.stated else None,
            "stated": self.stated,
            "basis": self.basis,
            "capped": self.capped,
            "missing_fields": list(self.missing_fields),
            "unverified_note": self.unverified_note or None,
            "phrase": self.phrase(),
            "worksheet": self.trace.render() if self.trace else None,
        }


# ── computation ─────────────────────────────────────────────────────────────

def _decimal(value: Any, what: str) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception as exc:
        raise BenefitError(f"{what} is not a number: {value!r}") from exc


def _needed(block: Mapping[str, Any], facts, *names: str) -> tuple[str, ...]:
    return tuple(n for n in names if n and not facts.has(n))


def _measure(block: Mapping[str, Any]) -> str | None:
    """The field a slab or tier is measured on.

    Accepts `measure` and `on`, and the reason is a genuine trap. PyYAML parses
    YAML 1.1, in which the bare key `on:` is the BOOLEAN TRUE — so a rule
    written with `on: capacity_kw` arrives as `{True: 'capacity_kw'}` and
    `block.get("on")` is None. The benefit then reports its input as missing
    and every user is asked for a field the pack already specified.

    Found by the PM-Surya Ghar tiers failing on a rule that reads correctly.
    `measure` is the spelling to use; `on` is still honoured because the same
    key works fine in a Python dict, which is how the unit tests write it.
    """
    if block.get("measure"):
        return str(block["measure"])
    if block.get("on"):
        return str(block["on"])
    if block.get(True):                 # `on:` in YAML 1.1
        raise BenefitError(
            "a benefit block used the YAML key `on:`, which PyYAML parses as "
            "the boolean True rather than the string 'on'. Spell it `measure:` "
            "instead — the rule reads correctly and silently measures nothing."
        )
    return None


def compute_benefit(rule: Mapping[str, Any], facts) -> BenefitAmount:
    """The rupee value of one scheme to one buyer.

    Falls back to the legacy scalar `max_benefit` when a rule carries no
    `benefit` block, so every CORE-009 rule keeps working unchanged. The two
    coexist deliberately: a flat deduction ceiling genuinely is a scalar, and
    rewriting `80EEB` as `{kind: flat, amount: 150000}` would add ceremony
    without adding truth.
    """
    block = rule.get("benefit")
    if not block:
        return BenefitAmount(
            amount=Money(rule.get("max_benefit") or 0),
            basis="statutory ceiling",
        )

    try:
        kind = BenefitKind(str(block.get("kind", "")).lower())
    except ValueError as exc:
        raise BenefitError(
            f"{rule.get('id')}: unknown benefit kind {block.get('kind')!r}. "
            f"Known kinds are {[k.value for k in BenefitKind]}."
        ) from exc

    if kind is BenefitKind.UNVERIFIED:
        note = " ".join(str(block.get("note", "")).split())
        if not note:
            raise BenefitError(
                f"{rule.get('id')}: an unverified benefit must say what has "
                f"not been verified and where to check it. An unexplained "
                f"'unverified' is indistinguishable from an oversight."
            )
        return BenefitAmount(stated=False, basis="not verified",
                             unverified_note=note)

    name = rule.get("name", rule.get("id", "benefit"))
    trace = Trace(f"{name} — amount")
    cap = Money(block["cap"]) if block.get("cap") is not None else None

    if kind is BenefitKind.FLAT:
        amount = trace.literal(name, Money(block["amount"]))
        return BenefitAmount(amount=amount, basis="flat amount", trace=trace)

    if kind is BenefitKind.PER_UNIT:
        unit_field = block.get("per")
        missing = _needed(block, facts, unit_field)
        if missing:
            return BenefitAmount(missing_fields=missing,
                                 basis=f"{block['rate']} per {block.get('unit', 'unit')}")
        units = _decimal(facts.get(unit_field), unit_field)
        per = Money(block["rate"])
        gross = trace.multiply(
            f"{per} per {block.get('unit', 'unit')} × {units}", per, units,
        )
        return _apply_cap(gross, cap, trace,
                          basis=f"{per} per {block.get('unit', 'unit')}")

    if kind is BenefitKind.PERCENTAGE:
        of_field = block.get("of")
        missing = _needed(block, facts, of_field)
        if missing:
            return BenefitAmount(missing_fields=missing,
                                 basis=f"{format_rate(_decimal(block['rate'], 'rate'))}% of cost")
        r = _decimal(block["rate"], "rate")
        base = Money(facts.get(of_field))
        gross = trace.multiply(
            f"{format_rate(r)}% of {of_field.replace('_', ' ')}", base, r,
        )
        return _apply_cap(gross, cap, trace,
                          basis=f"{format_rate(r)}% of cost")

    if kind is BenefitKind.TIERED:
        return _tiered(block, facts, trace, cap)

    # SLAB
    field_name = _measure(block)
    missing = _needed(block, facts, field_name)
    if missing:
        return BenefitAmount(missing_fields=missing, basis="capacity slab")
    value = _decimal(facts.get(field_name), field_name)
    bands = block.get("bands") or []
    if not bands:
        raise BenefitError(f"{rule.get('id')}: a slab benefit needs bands.")

    chosen: Mapping[str, Any] | None = None
    for band in bands:
        upto = band.get("upto")
        if upto is None or value <= _decimal(upto, "band.upto"):
            chosen = band
            break
    if chosen is None:
        chosen = bands[-1]

    amount = trace.literal(
        f"{field_name.replace('_', ' ')} {value} "
        f"→ {chosen.get('label', 'band')}",
        Money(chosen["amount"]),
    )
    return _apply_cap(amount, cap, trace, basis="capacity slab")


def _tiered(
    block: Mapping[str, Any], facts, trace: Trace, cap: Money | None,
) -> BenefitAmount:
    """Marginal rates per tier — like income tax slabs, not like a lookup.

    The distinction is not academic and PM-Surya Ghar is why this kind exists.
    Every secondary source summarises its CFA as "₹30,000 for 1 kW, ₹60,000 for
    2 kW, ₹78,000 for 3 kW and above", which reads like a slab table. It is not
    one. The scheme pays ₹30,000 per kWp on the first 2 kWp and ₹18,000 per kWp
    on the third, so the ministry's own worked example puts a 1.5 kW system at
    ₹45,000 — the slab reading gives ₹60,000, over by ₹15,000. A 2.5 kW system
    is ₹69,000 against the slab reading's ₹78,000.

    Since most residential installations are not whole numbers of kW, the slab
    model is wrong for the majority of the people it would be shown to, and it
    is wrong in the direction of promising money that will not arrive.
    """
    field_name = _measure(block)
    missing = _needed(block, facts, field_name)
    if missing:
        return BenefitAmount(missing_fields=missing, basis="tiered rate")

    value = _decimal(facts.get(field_name), field_name)
    tiers = block.get("tiers") or []
    if not tiers:
        raise BenefitError("a tiered benefit needs tiers.")

    unit = block.get("unit", "unit")
    parts: list[Money] = []
    floor = Decimal(0)
    for tier in tiers:
        ceiling = (
            value if tier.get("upto") is None
            else _decimal(tier["upto"], "tier.upto")
        )
        width = min(value, ceiling) - floor
        if width > 0:
            per = Money(tier["rate"])
            parts.append(trace.multiply(
                f"{tier.get('label', f'up to {ceiling} {unit}')} — "
                f"{per} per {unit} × {width}",
                per, width,
            ))
        floor = ceiling
        if value <= ceiling:
            break

    if not parts:
        return BenefitAmount(amount=ZERO, basis="tiered rate", trace=trace)
    total = parts[0] if len(parts) == 1 else trace.sum_of("Total", *parts)
    return _apply_cap(total, cap, trace, basis="tiered rate")


def _apply_cap(
    gross: Money, cap: Money | None, trace: Trace, *, basis: str,
) -> BenefitAmount:
    """Capping is a traced step, not a `min()`.

    A benefit that silently returns the cap looks identical to one that
    computed correctly and happened to land there. The worksheet is what tells
    a user their 3 kWh scooter hit a 2 kWh ceiling.
    """
    if cap is None:
        return BenefitAmount(amount=gross, basis=basis, trace=trace)
    if gross <= cap:
        return BenefitAmount(amount=gross, basis=basis, trace=trace)
    capped = trace.lesser_of(f"Capped at {cap}", gross, cap)
    return BenefitAmount(amount=capped, basis=f"{basis}, capped at {cap}",
                         trace=trace, capped=True)


__all__ = [
    "BenefitAmount",
    "BenefitError",
    "BenefitKind",
    "compute_benefit",
]
