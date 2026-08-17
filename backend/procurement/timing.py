"""When a purchase happens, and what that is worth — PRC-005.

THIS IS NOT A PRICE FORECAST, and the whole module is built so that it cannot
quietly become one.

The distinction it exists to hold
----------------------------------
There are two completely different claims a product can make about timing, and
they get muddled constantly:

    "The 80EEB window closes on 31 March 2023."       a dated fact
    "Prices are likely to fall after Diwali."          a prediction

The first is checkable, has a source, and has a rupee value that can be
computed exactly. The second is a guess about a market, and a tax product that
makes it has quietly become an investment advisor without the licence or the
competence. AGT-006 refuses securities advice; this refuses the softer version
of the same thing.

So a `Signal` carries no field for a future price. There is nowhere to put one.
The three computable kinds derive their rupee impact from the engines that
already know — the eligibility engine for a closing scheme, the costing model
for the depreciation boundary — and the fourth kind, `OBSERVED_PATTERN`,
carries `years_observed` and a rupee impact that is `None` BY TYPE.

Why observed patterns are here at all
--------------------------------------
Because "manufacturers discounted outgoing model-year stock in each of 2021,
2022, 2023 and 2024" is true, useful, and not a prediction. Dropping it would
be a different kind of dishonesty — pretending the pattern does not exist so as
to avoid the appearance of forecasting. Stating it with the years attached and
no rupee figure lets the reader draw their own conclusion, which is theirs to
draw.

The 31 March / 1 April boundary
--------------------------------
The one piece of timing advice in this whole product that is arithmetic rather
than judgement. An asset put to use for under 180 days gets HALF the normal
depreciation rate, so a 31 March purchase earns half a year's depreciation
immediately and a 1 April purchase earns a full year, twelve months later. For
a business buyer the difference is exact, computable and often large, and no
part of it depends on what anyone thinks a price will do.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any

from backend.core.costing.landed_cost import Purchase, compute_landed_cost
from backend.core.eligibility import Facts, Status, evaluate_all
from backend.core.provenance.money import ZERO, Money


class Kind(str, Enum):
    POLICY_CLIFF = "policy_cliff"        # a scheme window closes
    RATE_CHANGE = "rate_change"          # a statutory rate changes on a date
    TAX_BOUNDARY = "tax_boundary"        # 31 March / 1 April
    OBSERVED_PATTERN = "observed_pattern"  # historical, never a forecast

    @property
    def is_a_fact_about_the_future(self) -> bool:
        """True where the date is fixed in law or notification.

        An observed pattern is a fact about the PAST that a reader may choose
        to extrapolate. This engine does not extrapolate it for them.
        """
        return self is not Kind.OBSERVED_PATTERN


@dataclass(frozen=True, slots=True)
class Signal:
    """One dated, sourced fact that changes what a purchase costs.

    There is no field for a predicted price, a probability or a direction, and
    that absence is the design. A forecast has nowhere to live here.
    """

    kind: Kind
    label: str
    on: date | None
    detail: str
    source_url: str = ""
    impact: Money | None = None
    years_observed: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if self.kind is Kind.OBSERVED_PATTERN:
            if self.impact is not None:
                raise ValueError(
                    f"{self.label}: an observed pattern must not carry a rupee "
                    f"impact. Attaching one turns 'this happened in 2021-24' "
                    f"into 'this will be worth ₹X to you', which is a forecast "
                    f"wearing a fact's clothes."
                )
            if not self.years_observed:
                raise ValueError(
                    f"{self.label}: an observed pattern must state the years it "
                    f"was observed in. Without them it reads as a general "
                    f"truth about how the market behaves."
                )
        elif self.on is None:
            raise ValueError(
                f"{self.label}: a {self.kind.value} signal must carry the date "
                f"it takes effect. That date is the entire content of the "
                f"claim."
            )

    def days_away(self, today: date) -> int | None:
        return (self.on - today).days if self.on else None

    def sentence(self, today: date) -> str:
        """Rendered from a template per kind, never free-form.

        Templating is what keeps the language honest at scale: there is no
        place in this function where a sentence about what a price will do
        could be composed, because none of the templates has a slot for one.
        """
        if self.kind is Kind.OBSERVED_PATTERN:
            years = ", ".join(str(y) for y in self.years_observed)
            return (
                f"{self.label}: observed in {years}. This is a record of what "
                f"happened, not a statement about what will. {self.detail}"
            ).strip()

        away = self.days_away(today)
        when = self.on.strftime("%d %B %Y") if self.on else ""
        if away is not None and away < 0:
            timing = f"passed on {when}, {abs(away)} days ago"
        elif away == 0:
            timing = f"is today, {when}"
        else:
            timing = f"is {when}, {away} days away"

        worth = f" Worth {self.impact} on this purchase." if self.impact else ""
        return f"{self.label}: {timing}. {self.detail}{worth}".strip()

    def to_dict(self, today: date) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "label": self.label,
            "on": self.on.isoformat() if self.on else None,
            "days_away": self.days_away(today),
            "detail": self.detail,
            "source_url": self.source_url or None,
            "impact": self.impact.to_json() if self.impact else None,
            "impact_display": str(self.impact) if self.impact else None,
            "years_observed": list(self.years_observed),
            "is_a_forecast": False,
            "sentence": self.sentence(today),
        }


@dataclass(slots=True)
class Ledger:
    signals: list[Signal] = field(default_factory=list)
    today: date = field(default_factory=date.today)

    @property
    def upcoming(self) -> list[Signal]:
        return sorted(
            (s for s in self.signals
             if s.on is not None and s.on >= self.today),
            key=lambda s: s.on,      # type: ignore[arg-type,return-value]
        )

    @property
    def passed(self) -> list[Signal]:
        return sorted(
            (s for s in self.signals if s.on is not None and s.on < self.today),
            key=lambda s: s.on,      # type: ignore[arg-type,return-value]
            reverse=True,
        )

    @property
    def patterns(self) -> list[Signal]:
        return [s for s in self.signals if s.kind is Kind.OBSERVED_PATTERN]

    @property
    def quantified(self) -> Money:
        """What the dated signals are worth in total.

        Only the computable kinds contribute, because only they have a figure.
        An observed pattern cannot reach this number by construction.
        """
        out = ZERO
        for s in self.signals:
            if s.impact is not None:
                out = out + s.impact
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of": self.today.isoformat(),
            "upcoming": [s.to_dict(self.today) for s in self.upcoming],
            "passed": [s.to_dict(self.today) for s in self.passed],
            "observed_patterns": [s.to_dict(self.today) for s in self.patterns],
            "quantified_total": self.quantified.to_json(),
            "contains_forecasts": False,
        }


# ── the three computable kinds ──────────────────────────────────────────────

def scheme_cliffs(facts: Facts, *, today: date) -> list[Signal]:
    """Windows that close, taken from the eligibility engine rather than a list.

    Restating the dates here would give the product two sources of truth about
    when 80EEB shut, and the one nobody is looking at would rot.
    """
    out: list[Signal] = []
    for outcome in evaluate_all(facts):
        window_end = _window_end(outcome.rule_id)
        if outcome.status is Status.ELIGIBLE and window_end:
            out.append(Signal(
                kind=Kind.POLICY_CLIFF,
                label=f"{outcome.name} closes",
                on=window_end,
                detail=(
                    "You qualify today. This is a scheme window, not a market "
                    "guess — after this date the benefit is not available at "
                    "any price."
                ),
                impact=(
                    outcome.max_benefit
                    if outcome.amount_is_stated and outcome.amount_is_known
                    else None
                ),
                source_url=(
                    outcome.citation.source_url if outcome.citation else ""
                ) or "",
            ))
        elif outcome.status is Status.WINDOW_CLOSED and outcome.closed_on:
            out.append(Signal(
                kind=Kind.POLICY_CLIFF,
                label=f"{outcome.name} closed",
                on=outcome.closed_on,
                detail=outcome.reason or "The window has closed.",
                source_url=(
                    outcome.citation.source_url if outcome.citation else ""
                ) or "",
            ))
    return out


def _window_end(rule_id: str) -> date | None:
    from backend.core.eligibility.evaluator import _load_rules

    for rule in _load_rules():
        if rule["id"] != rule_id:
            continue
        for window in rule.get("windows", []):
            if "to" in window:
                raw = window["to"]
                return raw if isinstance(raw, date) else date.fromisoformat(str(raw))
    return None


def depreciation_boundary(
    purchase: Purchase, fy: str, *, today: date, cfg: dict[str, Any],
) -> Signal | None:
    """31 March against 1 April, computed both ways rather than asserted.

    The half-rate rule is the only timing effect in this product that is pure
    arithmetic. Both sides are actually recomputed through the costing model:
    stating "buy before 31 March to save tax" without the figure is advice, and
    with the figure it is a calculation the buyer can check.

    Returns None for a buyer this cannot affect. A salaried person buying a car
    for the school run has no depreciation, and telling them to hurry before
    31 March would be a fabricated urgency.

    The guard below is an early exit, not the safeguard — mutation-testing it
    showed the suite still passes with it removed, because the costing model
    emits no depreciation line for a non-business buyer and the impact comes
    out at zero either way. It is kept for the cost of not running the model
    for the majority of buyers, and the guarantee lives one layer down.
    """
    if not (purchase.is_business_use and purchase.depreciation_block):
        return None

    year_end = _fy_end(fy)
    if today > year_end:
        return None

    # Computed under THIS year's pack only, and only for the March side.
    #
    # The obvious implementation runs the model twice — 31 March under this
    # year's rules, 1 April under next year's — and subtracts. It cannot be
    # written, because next year's pack does not exist and `load_ruleset`
    # refuses to invent one. That refusal is right: reaching for the current
    # pack to stand in for FY 2027-28 would be assuming the Budget changes
    # nothing, which is the "no default financial year" rule broken from the
    # inside.
    #
    # It is also unnecessary. What the buyer is choosing between is a
    # half-rate deduction NOW and a full-rate deduction a year later, and over
    # the life of the asset the total is identical — the half not claimed in
    # year one returns through the written-down value. The only thing the date
    # changes is WHEN. So the figure worth stating is the deduction brought
    # forward by one year, which is exactly the first-year effect at half
    # rate, and that is computable from this year's pack alone.
    at_year_end = compute_landed_cost(
        _with(purchase, purchase_date=year_end, days_used_in_year=1), fy,
    )
    brought_forward = ZERO
    for line in at_year_end.lines:
        if line.label.startswith("First-year depreciation"):
            brought_forward = line.amount
    if brought_forward <= ZERO:
        return None

    threshold = int(cfg["depreciation"]["half_rate_if_used_under_days"])
    return Signal(
        kind=Kind.TAX_BOUNDARY,
        label="Financial year end — depreciation",
        on=year_end,
        detail=(
            f"Buying on or before {year_end:%d %B %Y} earns depreciation in "
            f"this financial year, at HALF the normal rate because the asset "
            f"will have been in use for under {threshold} days. Buying the "
            f"next day earns the full rate, but a year later. The half not "
            f"claimed now is not lost — it comes back through the "
            f"written-down value in later years, so this is a question of "
            f"WHEN the deduction lands, not whether. The figure below is the "
            f"tax brought forward by one year, not money saved."
        ),
        impact=brought_forward,
        source_url="https://www.incometaxindia.gov.in/",
    )


def rate_changes(gst_pack: dict[str, Any], *, today: date) -> list[Signal]:
    """Effective dates already sitting in the GST pack."""
    out: list[Signal] = []
    for schedule in gst_pack.get("schedules", []):
        on = date.fromisoformat(str(schedule["effective_from"]))
        abolished = schedule.get("abolished_slabs") or []
        if not abolished:
            continue
        pretty = ", ".join(f"{Decimal(str(a)) * 100:.0f}%" for a in abolished)
        out.append(Signal(
            kind=Kind.RATE_CHANGE,
            label=f"{schedule['name']} took effect",
            on=on,
            detail=(
                f"The {pretty} slab(s) were abolished. A quotation still "
                f"showing one of them is out of date, not a different opinion."
            ),
            source_url="https://cbic.gov.in/",
        ))
    return out


# ── helpers ─────────────────────────────────────────────────────────────────

def _fy_end(fy: str) -> date:
    start = int(fy.split("-")[0])
    return date(start + 1, 3, 31)


def _with(purchase: Purchase, **changes: Any) -> Purchase:
    from dataclasses import replace

    return replace(purchase, **changes)


def build_ledger(
    *,
    today: date,
    facts: Facts | None = None,
    purchase: Purchase | None = None,
    fy: str = "",
    cfg: dict[str, Any] | None = None,
    gst_pack: dict[str, Any] | None = None,
    patterns: list[Signal] | None = None,
) -> Ledger:
    """Everything dated that bears on this purchase, in one place."""
    signals: list[Signal] = []
    if facts is not None:
        signals.extend(scheme_cliffs(facts, today=today))
    if purchase is not None and fy and cfg is not None:
        boundary = depreciation_boundary(purchase, fy, today=today, cfg=cfg)
        if boundary is not None:
            signals.append(boundary)
    if gst_pack is not None:
        signals.extend(rate_changes(gst_pack, today=today))
    if patterns:
        signals.extend(patterns)
    return Ledger(signals=signals, today=today)


__all__ = [
    "Kind",
    "Ledger",
    "Signal",
    "build_ledger",
    "depreciation_boundary",
    "rate_changes",
    "scheme_cliffs",
]
