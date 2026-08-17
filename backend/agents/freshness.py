"""Answer-time source freshness — AGT-012.

The constraint that shapes this
--------------------------------
Naively re-fetching every cited source on every answer puts the network on the
critical path of every response. A tax answer that takes eleven seconds because
it checked six government portals is not a better answer.

So: check the CACHE at answer time, and never the network. The cache is filled
by a background sweep. Three outcomes, and the third is the important one:

    FRESH     checked recently, nothing changed          → answer normally
    STALE     not checked lately, or the source moved     → answer, downgrade
                                                            confidence, badge it
    UNKNOWN   never checked                               → answer, say so

A network failure never blocks an answer
-----------------------------------------
It cannot, because there is no network call here. That is not a resilience
feature bolted on, it is the design: the only thing that can fail at answer
time is a dictionary lookup. The background sweep can fail all it likes and the
worst outcome is that facts age into STALE, which is exactly the honest state.

A detected change flags, it does not recompute
-----------------------------------------------
Silently recomputing means a user's answer changes between two readings with no
explanation. The badge says the source moved and which rule it affects; a human
decides whether the answer should change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any

DEFAULT_FRESH_WINDOW_DAYS = 30
DEFAULT_STALE_WINDOW_DAYS = 180


class Freshness(str, Enum):  # noqa: UP042
    FRESH = "fresh"
    STALE = "stale"
    CHANGED = "changed"
    UNKNOWN = "unknown"

    @property
    def downgrades_confidence(self) -> bool:
        return self is not Freshness.FRESH

    @property
    def badge(self) -> str:
        return {
            Freshness.FRESH: "",
            Freshness.STALE: "not re-checked recently",
            Freshness.CHANGED: "⚠ source has changed since we read it",
            Freshness.UNKNOWN: "never re-checked",
        }[self]


@dataclass(frozen=True, slots=True)
class FreshnessVerdict:
    url: str
    state: Freshness
    checked_on: date | None
    age_days: int | None
    affects_rules: tuple[str, ...] = ()
    detail: str = ""

    @property
    def blocks_answer(self) -> bool:
        """Never. Freshness downgrades confidence; it does not withhold an
        answer. A user with a stale-but-labelled figure is better served than a
        user with an error page."""
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "state": self.state.value,
            "badge": self.state.badge,
            "checked_on": self.checked_on.isoformat() if self.checked_on else None,
            "age_days": self.age_days,
            "downgrades_confidence": self.state.downgrades_confidence,
            "affects_rules": list(self.affects_rules),
            "detail": self.detail,
        }


@dataclass(slots=True)
class FreshnessCache:
    """What the background sweep last found, per URL.

    Deliberately a plain in-memory mapping with no fetch method. A cache that
    could fetch would eventually be asked to, and the network would be back on
    the critical path.
    """

    entries: dict[str, dict[str, Any]] = field(default_factory=dict)

    def record(
        self,
        url: str,
        *,
        checked_on: date,
        changed: bool = False,
        affects_rules: tuple[str, ...] = (),
    ) -> None:
        self.entries[url] = {
            "checked_on": checked_on,
            "changed": changed,
            "affects_rules": tuple(affects_rules),
        }

    def get(self, url: str) -> dict[str, Any] | None:
        return self.entries.get(url)


def check_freshness(
    url: str,
    cache: FreshnessCache,
    *,
    today: date,
    fresh_window_days: int = DEFAULT_FRESH_WINDOW_DAYS,
    stale_window_days: int = DEFAULT_STALE_WINDOW_DAYS,
) -> FreshnessVerdict:
    """A dictionary lookup. No network, by construction."""
    entry = cache.get(url)
    if entry is None:
        return FreshnessVerdict(
            url, Freshness.UNKNOWN, None, None,
            detail=(
                "This source has never been re-checked since it was first read. "
                "The figure may still be right; nobody has confirmed it lately."
            ),
        )

    age = (today - entry["checked_on"]).days

    if entry["changed"]:
        return FreshnessVerdict(
            url, Freshness.CHANGED, entry["checked_on"], age,
            affects_rules=entry["affects_rules"],
            detail=(
                f"This source changed since the figure was read from it. The "
                f"figure has NOT been recomputed — a number that moves without "
                f"explanation is worse than one that is stale and labelled. "
                f"{len(entry['affects_rules'])} rule(s) are affected."
            ),
        )

    if age > stale_window_days:
        return FreshnessVerdict(
            url, Freshness.STALE, entry["checked_on"], age,
            detail=(
                f"Last re-checked {age} days ago, beyond the "
                f"{stale_window_days}-day window. Probably still correct; "
                f"confirm before relying on it."
            ),
        )

    if age > fresh_window_days:
        return FreshnessVerdict(
            url, Freshness.STALE, entry["checked_on"], age,
            detail=f"Last re-checked {age} days ago.",
        )

    return FreshnessVerdict(
        url, Freshness.FRESH, entry["checked_on"], age,
        detail=f"Re-checked {age} day(s) ago; unchanged.",
    )


@dataclass(slots=True)
class AnswerFreshness:
    """The freshness of every source behind one answer."""

    verdicts: list[FreshnessVerdict] = field(default_factory=list)

    @property
    def worst(self) -> Freshness:
        for state in (Freshness.CHANGED, Freshness.UNKNOWN, Freshness.STALE):
            if any(v.state is state for v in self.verdicts):
                return state
        return Freshness.FRESH

    @property
    def confidence_penalty(self) -> str:
        """What this costs the confidence score, as a decimal string.

        A changed source costs most because it is the only state where the
        underlying fact may actually be wrong rather than merely unconfirmed.
        """
        return {
            Freshness.CHANGED: "0.25",
            Freshness.UNKNOWN: "0.10",
            Freshness.STALE: "0.05",
            Freshness.FRESH: "0.00",
        }[self.worst]

    @property
    def changed(self) -> list[FreshnessVerdict]:
        return [v for v in self.verdicts if v.state is Freshness.CHANGED]

    def to_dict(self) -> dict[str, Any]:
        return {
            "worst": self.worst.value,
            "badge": self.worst.badge,
            "confidence_penalty": self.confidence_penalty,
            "blocks_answer": False,
            "sources": [v.to_dict() for v in self.verdicts],
        }


def check_answer(
    urls: list[str],
    cache: FreshnessCache,
    *,
    today: date,
    **kw: Any,
) -> AnswerFreshness:
    """Check every source behind an answer. Cannot fail, cannot block."""
    return AnswerFreshness(
        [check_freshness(u, cache, today=today, **kw) for u in urls]
    )


__all__ = [
    "AnswerFreshness",
    "Freshness",
    "FreshnessCache",
    "FreshnessVerdict",
    "check_answer",
    "check_freshness",
]
