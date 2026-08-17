"""Tearing a quotation apart line by line — PRC-006.

Why this is the most useful thing in Phase 6
---------------------------------------------
Everything else in procurement reasons about a hypothetical purchase. This one
works on the piece of paper the buyer is holding, with their actual price on
it, in the twenty minutes before they sign. That is where a rupee figure is
worth something.

It is also where padding hides, and it hides in the NAMING. Dealers call the
same charge a dozen things. A line called "handling" is negotiable; a line
called "RTO" is not. A quote that calls a handling fee "RTO charges" is relying
on the buyer not knowing the difference, and the whole value of this module is
in telling them apart.

The distinction that shapes the output
---------------------------------------
Two totals, never one:

    overcharged   a statutory figure is wrong. Defensible, arguable in writing.
    negotiable    a charge with no statutory basis. Legal, and up for discussion.

Adding them would hand a buyer a single number to walk into a showroom with,
part of which is a fee they will be told — correctly — that they agreed to. The
argument then collapses and so does the credible half of it. Keeping them apart
is what makes the defensible number defensible.

Silence is not approval
------------------------
A line this engine cannot check is reported as UNCHECKED, not omitted. "Three
issues found" reads as "everything else is fine", and a teardown that quietly
drops the extended warranty it knows nothing about has told the buyer something
false by omission. `Teardown.coverage()` states what was and was not examined.

What this does not do
----------------------
It has no opinion on whether a price is high. Whether ₹8.4 lakh is a good price
for that car is a market judgement, and this module makes none — it says only
that a statutory line disagrees with the statute, or that a charge has no
statutory basis. The same restraint as PRC-005 and PRC-007.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any

from backend.core.costing.landed_cost import LandedCost
from backend.core.provenance.money import ZERO, Money, format_rate
from backend.core.provenance.trace import Trace


class Verdict(str, Enum):
    WRONG_RATE = "wrong_rate"
    EXCEEDS_STATUTORY = "exceeds_statutory"
    NOT_APPLICABLE = "not_applicable"
    NO_STATUTORY_BASIS = "no_statutory_basis"
    ARITHMETIC = "arithmetic"
    UNCHECKED = "unchecked"
    NOT_A_COST = "not_a_cost"

    @property
    def is_defensible(self) -> bool:
        """Whether the buyer can point at a rule and say "this is wrong".

        NO_STATUTORY_BASIS is deliberately excluded: a handling fee is legal.
        Calling it an overcharge is itself an error, and one that would be
        corrected in the showroom in front of the buyer.
        """
        return self in (
            Verdict.WRONG_RATE,
            Verdict.EXCEEDS_STATUTORY,
            Verdict.NOT_APPLICABLE,
            Verdict.ARITHMETIC,
        )


@dataclass(frozen=True, slots=True)
class QuoteLine:
    label: str
    amount: Money


@dataclass(slots=True)
class Quote:
    """What the dealer handed over."""

    item: str
    lines: list[QuoteLine]
    stated_total: Money | None = None
    quoted_on: date | None = None
    dealer: str = ""

    @property
    def sum_of_lines(self) -> Money:
        out = ZERO
        for line in self.lines:
            out = out + line.amount
        return out


@dataclass(frozen=True, slots=True)
class Finding:
    verdict: Verdict
    label: str
    quoted: Money
    expected: Money | None
    detail: str

    @property
    def delta(self) -> Money:
        """What the buyer is being asked for over the computed figure.

        Never negative. A dealer charging LESS road tax than the schedule is
        not a finding against them, and reporting it as a negative overcharge
        would net it off against a real one somewhere else in the quote.
        """
        if self.expected is None:
            return ZERO
        gap = self.quoted - self.expected
        return gap if gap > ZERO else ZERO

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "label": self.label,
            "quoted": self.quoted.to_json(),
            "quoted_display": str(self.quoted),
            "expected": self.expected.to_json() if self.expected else None,
            "expected_display": str(self.expected) if self.expected else None,
            "delta": self.delta.to_json(),
            "delta_display": str(self.delta),
            "defensible": self.verdict.is_defensible,
            "detail": self.detail,
        }


@dataclass(slots=True)
class Teardown:
    quote: Quote
    findings: list[Finding] = field(default_factory=list)
    checked: list[str] = field(default_factory=list)
    trace: Trace | None = None

    @property
    def overcharged(self) -> Money:
        out = ZERO
        for f in self.findings:
            if f.verdict.is_defensible:
                out = out + f.delta
        return out

    @property
    def negotiable(self) -> Money:
        out = ZERO
        for f in self.findings:
            if f.verdict is Verdict.NO_STATUTORY_BASIS:
                out = out + f.quoted
        return out

    @property
    def not_a_cost(self) -> Money:
        """Money in the quote that is not money you lose — TCS, chiefly."""
        out = ZERO
        for f in self.findings:
            if f.verdict is Verdict.NOT_A_COST:
                out = out + f.quoted
        return out

    @property
    def unchecked(self) -> list[Finding]:
        return [f for f in self.findings if f.verdict is Verdict.UNCHECKED]

    def coverage(self) -> str:
        """What was examined, said out loud.

        Without this, a short findings list reads as a clean bill of health for
        the whole quote, and the lines nobody could check are exactly the ones
        a buyer most needs to ask about.
        """
        if not self.unchecked:
            return (
                f"Every line on this quote was checked against a computed "
                f"figure or a rule ({len(self.quote.lines)} lines)."
            )
        names = ", ".join(f.label for f in self.unchecked)
        return (
            f"{len(self.checked)} of {len(self.quote.lines)} lines were checked "
            f"against a computed figure. These were not, because nothing here "
            f"can price them — ask what they are for: {names}."
        )

    def headline(self) -> str:
        parts: list[str] = []
        if self.overcharged > ZERO:
            parts.append(f"{self.overcharged} above the statutory figures")
        if self.negotiable > ZERO:
            parts.append(f"{self.negotiable} in charges with no statutory basis")
        if not parts:
            return "Nothing on this quote disagrees with the statutory figures."
        return " and ".join(parts) + "."

    def to_dict(self) -> dict[str, Any]:
        return {
            "item": self.quote.item,
            "dealer": self.quote.dealer or None,
            "quoted_on": self.quote.quoted_on.isoformat() if self.quote.quoted_on else None,
            "stated_total": (
                self.quote.stated_total.to_json() if self.quote.stated_total else None
            ),
            "overcharged": self.overcharged.to_json(),
            "overcharged_display": str(self.overcharged),
            "negotiable": self.negotiable.to_json(),
            "negotiable_display": str(self.negotiable),
            "not_a_cost": self.not_a_cost.to_json(),
            "findings": [f.to_dict() for f in self.findings],
            "coverage": self.coverage(),
            "headline": self.headline(),
            "worksheet": self.trace.render() if self.trace else None,
        }


# ── matching ────────────────────────────────────────────────────────────────

def _norm(text: str) -> str:
    return " ".join(text.lower().replace("&", " and ").split())


def classify(label: str, cfg: dict[str, Any]) -> tuple[str, str]:
    """(kind, matched term). Longest term first, so 'rto tax' beats 'rto'.

    Substring matching on a normalised label, because a quote line reads
    "RTO / Road Tax & Registration" and no exact table will ever cover that.
    The longest-first ordering is what stops "rto" claiming a line that says
    "rto tax" when the two map to different computed figures.
    """
    block = cfg["quote_teardown"]
    text = _norm(label)

    best_kind, best_term = "", ""
    for kind, terms in block["statutory_terms"].items():
        for term in terms:
            t = _norm(term)
            if t in text and len(t) > len(best_term):
                best_kind, best_term = kind, t
    if best_kind:
        return best_kind, best_term

    for term in block["no_statutory_basis"]:
        t = _norm(term)
        if t in text and len(t) > len(best_term):
            best_kind, best_term = "no_statutory_basis", t
    return best_kind or "unknown", best_term


def _model_line(landed: LandedCost, prefix: str) -> Money | None:
    for line in landed.lines:
        if _norm(line.label).startswith(_norm(prefix)) and not line.is_deduction:
            return line.amount
    return None


def _model_gst_rate(landed: LandedCost) -> Decimal | None:
    base = landed.purchase.ex_showroom
    gst = _model_line(landed, "GST")
    if gst is None or base <= ZERO:
        return None
    return (gst.amount / base.amount).quantize(Decimal("0.0001"))


# ── the teardown ────────────────────────────────────────────────────────────

def tear_down(
    quote: Quote,
    landed: LandedCost,
    *,
    cfg: dict[str, Any],
    gst_pack: dict[str, Any] | None = None,
) -> Teardown:
    """Compare a real quotation against the computed landed cost.

    Takes an already-computed `LandedCost` rather than computing one, so this
    module cannot drift from the cost model — there is exactly one place that
    knows what road tax in Karnataka is, and it is not here.
    """
    trace = Trace(f"Quote teardown — {quote.item}")
    findings: list[Finding] = []
    checked: list[str] = []

    # ── does the quote add up ───────────────────────────────────────────────
    if quote.stated_total is not None:
        summed = trace.sum_of(
            "Sum of quoted lines", *[line.amount for line in quote.lines],
        )
        if summed != quote.stated_total:
            findings.append(Finding(
                Verdict.ARITHMETIC, "Quoted total", quote.stated_total, summed,
                f"The lines on this quote add up to {summed}, but the total "
                f"reads {quote.stated_total}. Ask which is right before "
                f"anything else — every other figure below is computed against "
                f"the lines.",
            ))

    seen_kinds: set[str] = set()
    for line in quote.lines:
        kind, term = classify(line.label, cfg)
        seen_kinds.add(kind)

        if kind == "gst":
            findings.extend(_check_gst(line, landed, gst_pack, trace))
            checked.append(line.label)
        elif kind in ("road_tax", "registration"):
            model = _model_line(landed, "Road tax" if kind == "road_tax" else "Registration")
            if model is None:
                findings.append(_unchecked(line, "no computed figure for it"))
            else:
                checked.append(line.label)
                if line.amount > model:
                    findings.append(Finding(
                        Verdict.EXCEEDS_STATUTORY, line.label, line.amount, model,
                        f"The schedule for this state and this vehicle gives "
                        f"{model}. The quote asks {line.amount}. Ask what the "
                        f"difference is for — if it is a service charge, it "
                        f"belongs on its own line.",
                    ))
        elif kind == "tcs":
            findings.append(_check_tcs(line, landed, cfg, trace))
            checked.append(line.label)
        elif kind == "insurance":
            # Insurance is a real cost from a third party at a price this
            # engine does not set. Recognised, not judged.
            checked.append(line.label)
        elif kind == "no_statutory_basis":
            findings.append(Finding(
                Verdict.NO_STATUTORY_BASIS, line.label, line.amount, None,
                f"There is no statute behind a {term!r} charge. It is not "
                f"improper and the dealer may well not remove it, but it is "
                f"the part of this quote that is open to discussion, unlike "
                f"GST or road tax.",
            ))
            checked.append(line.label)
        elif kind == "unknown":
            findings.append(_unchecked(line, "nothing here can price it"))

    return Teardown(quote=quote, findings=findings, checked=checked, trace=trace)


def _unchecked(line: QuoteLine, why: str) -> Finding:
    return Finding(
        Verdict.UNCHECKED, line.label, line.amount, None,
        f"Not checked — {why}. That is not the same as saying it is fair; ask "
        f"what it covers.",
    )


def _check_gst(
    line: QuoteLine, landed: LandedCost, gst_pack: dict[str, Any] | None,
    trace: Trace,
) -> list[Finding]:
    """The flagship check.

    GST 2.0 abolished the 12% and 28% slabs in September 2025 and dealer
    software has not universally caught up, so a quote arriving today at 28% is
    common and is simply wrong. It is also the largest single error available:
    28% against 18% on a ₹10 lakh vehicle is a lakh of rupees.
    """
    base = landed.purchase.ex_showroom
    if base <= ZERO:
        return [_unchecked(line, "the quote carries no ex-showroom price")]

    quoted_rate = (line.amount.amount / base.amount).quantize(Decimal("0.0001"))
    expected_rate = _model_gst_rate(landed)

    abolished = []
    if gst_pack:
        schedule = max(
            (s for s in gst_pack["schedules"]
             if date.fromisoformat(str(s["effective_from"])) <= (
                 landed.purchase.purchase_date)),
            key=lambda s: date.fromisoformat(str(s["effective_from"])),
            default=None,
        )
        if schedule:
            abolished = [Decimal(str(a)) for a in schedule.get("abolished_slabs", [])]

    if quoted_rate in abolished:
        detail = (
            f"This is GST at {format_rate(quoted_rate)}% of the ex-showroom "
            f"price — a slab that no longer exists. GST 2.0 abolished it on "
            f"22 September 2025, and dealer software that has not been updated "
            f"still quotes it."
        )
        expected = None
        if expected_rate is not None:
            expected = landed.purchase.ex_showroom * expected_rate
            detail += (
                f" The applicable rate for this item is "
                f"{format_rate(expected_rate)}%, which is {expected}."
            )
        return [Finding(Verdict.WRONG_RATE, line.label, line.amount, expected,
                        detail)]

    if expected_rate is not None and quoted_rate != expected_rate:
        expected = landed.purchase.ex_showroom * expected_rate
        return [Finding(
            Verdict.WRONG_RATE, line.label, line.amount, expected,
            f"GST here works out at {format_rate(quoted_rate)}% of the "
            f"ex-showroom price. The rate for this category on "
            f"{landed.purchase.purchase_date:%d %B %Y} is "
            f"{format_rate(expected_rate)}%.",
        )]
    return []


def _check_tcs(
    line: QuoteLine, landed: LandedCost, cfg: dict[str, Any], trace: Trace,
) -> Finding:
    """TCS is not a cost, and saying so is the point.

    It is the buyer's own tax collected early: creditable against their income
    tax or refundable, and visible in Form 26AS. Listing it beside road tax and
    insurance makes the on-road price look higher than the money the buyer is
    actually out, and almost nobody claims it back.
    """
    rules = cfg["quote_teardown"]["tcs"]
    threshold = Money(rules["threshold"])
    rate = Decimal(str(rules["rate"]))
    consideration = landed.purchase.ex_showroom + landed.purchase.accessories

    if consideration <= threshold:
        return Finding(
            Verdict.NOT_APPLICABLE, line.label, line.amount, ZERO,
            f"s.{rules['legacy_section']} applies where the consideration "
            f"exceeds {threshold}. This one is {consideration}, so no TCS is "
            f"collectable. Ask for it to be removed.",
        )

    expected = consideration * rate
    if line.amount != expected:
        return Finding(
            Verdict.WRONG_RATE, line.label, line.amount, expected,
            f"TCS under s.{rules['legacy_section']} is "
            f"{format_rate(rate)}% of the whole consideration of "
            f"{consideration} — {expected}, not {line.amount}. Note that it "
            f"applies to the entire amount, not only the excess over "
            f"{threshold}.",
        )
    return Finding(
        Verdict.NOT_A_COST, line.label, line.amount, expected,
        " ".join(str(rules["creditable_note"]).split()),
    )


__all__ = [
    "Finding",
    "Quote",
    "QuoteLine",
    "Teardown",
    "Verdict",
    "classify",
    "tear_down",
]
