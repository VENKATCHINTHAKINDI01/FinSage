"""Source tiering — PRC-002 (the pure half).

Lives in core because these are pure data types with no I/O: a tier, a dated
fact, and a cost line that refuses to exist if its source is not authoritative
enough. The FETCHERS — the things that actually call parivahan or CBIC — live
in `backend/procurement/`, which core is forbidden to import.

That split was forced by the purity contract, and it was right to force it. The
enforcement of "a Tier-3 source cannot produce a figure" belongs beside Money
and Trace, not beside the HTTP clients.


The rule, and why it is a type and not a convention
----------------------------------------------------
A Tier-3 source — a marketplace listing, a review site, a news article, a forum
post — may add context to a purchase decision. It may NEVER produce a rupee
figure in a cost breakdown.

"Never" enforced by a code review is a rule that survives until the first
deadline. So `CostLine` cannot be constructed from a Tier-3 fact at all: the
constructor raises. The check is on the type of the thing, not on the diligence
of the person writing the call site.

That matters because procurement is where the temptation is strongest. Official
sources give you GST and road tax; they do not give you the actual on-road price
a dealer is quoting this week. The pull toward "well, this listing says ₹8.4
lakh" is constant, and the whole credibility of a cost breakdown rests on
refusing it.

Freshness is per source, because the facts age differently
-----------------------------------------------------------
A GST rate is stable for months. A gold price is stale in an hour. Circle rates
move once a year or two. One global TTL would either hammer stable endpoints or
serve hour-old gold prices as current, so each source declares its own.

Staleness serves, it does not break
------------------------------------
A stale cached fact is served with a visible badge rather than failing the
request. A user with a labelled 40-day-old GST rate is better served than a user
with an error page — the rate almost certainly has not moved, and if it has, the
badge is what tells them to check.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from enum import IntEnum
from typing import Any

from backend.core.provenance.money import Money


class Tier(IntEnum):
    """Lower is more authoritative.

    An IntEnum so `tier <= Tier.OEM` reads naturally and sorts correctly — the
    ordering is the point, not the labels.
    """

    OFFICIAL = 1      # cbic, incometax, parivahan, state transport, RERA, IBJA
    OEM_OR_BANK = 2   # manufacturer price list, dealer quotation, bank rate card
    AGGREGATOR = 3    # marketplace, review site, news, forum

    @property
    def may_drive_a_cost_line(self) -> bool:
        return self <= Tier.OEM_OR_BANK

    @property
    def label(self) -> str:
        return {
            Tier.OFFICIAL: "official",
            Tier.OEM_OR_BANK: "manufacturer or bank",
            Tier.AGGREGATOR: "unverified aggregator",
        }[self]


# Per-source freshness. A single global TTL would either hammer stable
# endpoints or serve hour-old gold as current.
TTL_DAYS: dict[str, Decimal] = {
    "gst": Decimal(30),
    "state_ev_policy": Decimal(7),
    "gold_rate": Decimal(1) / Decimal(24),   # one hour
    "circle_rate": Decimal(90),
    "road_tax": Decimal(90),
    "stamp_duty": Decimal(90),
    "rera": Decimal(30),
    "bank_rate_card": Decimal(7),
    "oem_price_list": Decimal(7),
}
DEFAULT_TTL_DAYS = Decimal(30)


class Tier3CannotCost(Exception):
    """A Tier-3 fact was used to produce a rupee figure.

    Deliberately an exception at construction, not a validation flag. A flag can
    be ignored; a constructor that refuses cannot.
    """


class UndatedFact(Exception):
    """A fact arrived without the date it was fetched."""


@dataclass(frozen=True, slots=True)
class SourcedFact:
    """One thing read from one place at one time."""

    key: str                  # "gst.electric_vehicle", "road_tax.KA.ev"
    value: Any
    source_url: str
    tier: Tier
    fetched_on: date
    source_kind: str = ""     # keys TTL_DAYS
    title: str = ""

    def __post_init__(self) -> None:
        if not self.fetched_on:
            raise UndatedFact(
                f"{self.key} arrived without a fetch date. A price or rate is "
                f"only true as of a date — GST 2.0 restructured the whole "
                f"schedule on one day in September 2025."
            )

    @property
    def ttl_days(self) -> Decimal:
        return TTL_DAYS.get(self.source_kind, DEFAULT_TTL_DAYS)

    def age_days(self, today: date) -> int:
        return (today - self.fetched_on).days

    def is_stale(self, today: date) -> bool:
        return Decimal(self.age_days(today)) > self.ttl_days

    def badge(self, today: date) -> str:
        """What the UI must show beside anything derived from this."""
        parts = []
        if self.tier is Tier.AGGREGATOR:
            parts.append("unverified — context only, not a cost")
        if self.is_stale(today):
            parts.append(f"{self.age_days(today)} days old, not re-checked")
        return " · ".join(parts)

    def to_dict(self, today: date | None = None) -> dict[str, Any]:
        out = {
            "key": self.key,
            "value": str(self.value),
            "source_url": self.source_url,
            "tier": int(self.tier),
            "tier_label": self.tier.label,
            "may_drive_a_cost_line": self.tier.may_drive_a_cost_line,
            "fetched_on": self.fetched_on.isoformat(),
            "as_of": f"as of {self.fetched_on.strftime('%d %B %Y')}",
        }
        if today is not None:
            out["stale"] = self.is_stale(today)
            out["badge"] = self.badge(today)
        return out


@dataclass(frozen=True, slots=True)
class CostLine:
    """One rupee figure in a breakdown, and the fact that produced it.

    The constructor is the enforcement point for the whole feature. There is no
    way to build a cost line from a Tier-3 fact, so there is no way for a
    marketplace listing to reach a total.
    """

    label: str
    amount: Money
    fact: SourcedFact
    is_deduction: bool = False

    def __post_init__(self) -> None:
        if not self.fact.tier.may_drive_a_cost_line:
            raise Tier3CannotCost(
                f"{self.label!r} was costed from {self.fact.source_url}, which "
                f"is tier {int(self.fact.tier)} ({self.fact.tier.label}). "
                f"Tier-3 sources may add context to a decision but must never "
                f"produce a figure in a cost breakdown. Find an official or "
                f"manufacturer source for this line, or drop the line."
            )

    @property
    def signed(self) -> Money:
        return -self.amount if self.is_deduction else self.amount

    def to_dict(self, today: date | None = None) -> dict[str, Any]:
        return {
            "label": self.label,
            "amount": self.amount.to_json(),
            "display": str(self.amount),
            "is_deduction": self.is_deduction,
            "source": self.fact.to_dict(today),
        }


@dataclass(slots=True)
class SourceCache:
    """Fetched facts, keyed by fact key.

    Serving stale is deliberate. A user with a labelled 40-day-old GST rate is
    better served than a user with an error page: the rate has almost certainly
    not moved, and the badge is what tells them to check if it matters.
    """

    facts: dict[str, SourcedFact] = field(default_factory=dict)

    def put(self, fact: SourcedFact) -> SourcedFact:
        self.facts[fact.key] = fact
        return fact

    def get(self, key: str) -> SourcedFact | None:
        return self.facts.get(key)

    def require(self, key: str) -> SourcedFact:
        """For a cost line, where absence must not be papered over."""
        fact = self.facts.get(key)
        if fact is None:
            raise KeyError(
                f"no source cached for {key!r}. A cost line cannot be built "
                f"from an assumption — gather the fact or omit the line."
            )
        return fact

    def stale(self, today: date) -> list[SourcedFact]:
        return [f for f in self.facts.values() if f.is_stale(today)]

    def context_only(self) -> list[SourcedFact]:
        """Tier-3 facts, which the UI must badge and never total."""
        return [f for f in self.facts.values() if not f.tier.may_drive_a_cost_line]


@dataclass(frozen=True, slots=True)
class CanaryResult:
    """A nightly liveness check on one Tier-1 fetcher."""

    source_kind: str
    url: str
    ok: bool
    checked_on: date
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_kind": self.source_kind,
            "url": self.url,
            "ok": self.ok,
            "checked_on": self.checked_on.isoformat(),
            "detail": self.detail,
        }


def canary_verdict(results: list[CanaryResult]) -> dict[str, Any]:
    """What the nightly sweep should report.

    A failing fetcher does not break the product — the cache keeps serving with
    a staleness badge. It does mean nobody will notice the rate has moved, which
    is why the failure has to surface somewhere a human looks.
    """
    failed = [r for r in results if not r.ok]
    return {
        "checked": len(results),
        "failed": [r.to_dict() for r in failed],
        "healthy": not failed,
        "message": (
            "All Tier-1 fetchers responded."
            if not failed
            else (
                f"{len(failed)} Tier-1 fetcher(s) failed. Cached facts continue "
                f"to serve with a staleness badge, so nothing is broken — but "
                f"nobody will see a rate change in these sources until this is "
                f"fixed."
            )
        ),
    }


def next_refresh_due(fact: SourcedFact) -> date:
    return fact.fetched_on + timedelta(days=int(fact.ttl_days) or 1)


__all__ = [
    "DEFAULT_TTL_DAYS",
    "TTL_DAYS",
    "CanaryResult",
    "CostLine",
    "SourceCache",
    "SourcedFact",
    "Tier",
    "Tier3CannotCost",
    "UndatedFact",
    "canary_verdict",
    "next_refresh_due",
]
