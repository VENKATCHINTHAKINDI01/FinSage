"""The citation ledger — PLN-007.

Every rupee figure the product shows must be click-through to *why*. A citation
alone is not enough for that: `cite("87A", "2026-27")` knows the section and the
year but not where the number was read from or when anyone last checked. Those
live in the rule pack's `meta` block. The ledger joins them.

The invariant
-------------
**An undated figure cannot be displayed.** Not "is displayed with a warning" —
cannot be built at all. `LedgerEntry` raises on construction without a
verification date, so a figure with no provenance fails in the engine rather
than rendering as a bare number a user might act on. "GST is 5%" is only true as
of a date; the whole schedule was restructured in September 2025.

Both numbering schemes, always
------------------------------
For FY 2026-27 onward the governing Act is the Income-tax Act 2025, whose
section numbers differ from the 1961 Act everyone knows. A ledger entry carries
both, and where the 1961→2025 mapping is unverified it says *provisionally*
rather than asserting the new number. That is the same discipline `cite()`
applies, carried through to the surface the user actually reads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from backend.core.provenance.citation import Citation
from backend.core.provenance.money import Money
from backend.core.provenance.trace import Step, Trace
from backend.core.rules.loader import TaxRuleset, load_ruleset


class UndatedFigure(Exception):
    """A figure was assembled without a verification date.

    Deliberately an exception rather than a flag. A figure whose provenance is
    unknown must not reach a user at all — the whole point of the ledger is that
    the absence of a date is a bug, not a display state.
    """


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """One displayed figure, and everything behind it."""

    label: str
    value: Money
    fy: str
    act: str
    verified_on: date
    rule_id: str | None = None
    section: str | None = None
    legacy_section: str | None = None
    source_urls: tuple[str, ...] = ()
    note: str = ""
    is_assumption: bool = False

    def __post_init__(self) -> None:
        if self.verified_on is None:
            raise UndatedFigure(
                f"{self.label!r} has no verification date, so it cannot be "
                f"displayed. Every figure shown to a user must carry the date "
                f"its rule was last checked."
            )
        if not self.section and not self.legacy_section and not self.rule_id:
            raise UndatedFigure(
                f"{self.label!r} has neither a section nor a rule id, so there "
                f"is nothing for a user to click through to."
            )

    @property
    def citation_display(self) -> str:
        """Both numbering schemes where both are known."""
        if self.section and self.legacy_section:
            body = f"s.{self.section} (formerly s.{self.legacy_section})"
        elif self.section or self.legacy_section:
            body = f"s.{self.section or self.legacy_section}"
        else:
            body = self.rule_id or "rule pack"
        return f"{self.act} · {body} · FY {self.fy}"

    @property
    def shows_both_numbering_schemes(self) -> bool:
        return bool(self.section and self.legacy_section)

    def age_days(self, today: date) -> int:
        return (today - self.verified_on).days

    def is_stale(self, today: date, window_days: int = 180) -> bool:
        return self.age_days(today) > window_days

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "value": self.value.to_json(),
            # str(Money) is the single formatting authority — symbol and
            # Indian digit grouping together. `indian_format()` omits the ₹,
            # which would leave the UI adding it and two layers deciding how
            # money looks.
            "display": str(self.value),
            "fy": self.fy,
            "act": self.act,
            "section": self.section,
            "legacy_section": self.legacy_section,
            "rule_id": self.rule_id,
            "citation": self.citation_display,
            "verified_on": self.verified_on.isoformat(),
            "source_urls": list(self.source_urls),
            "note": self.note or None,
            "is_assumption": self.is_assumption,
        }


@dataclass(slots=True)
class Ledger:
    """Every figure in one answer, keyed for click-through from the UI."""

    fy: str
    entries: list[LedgerEntry] = field(default_factory=list)

    def add(self, entry: LedgerEntry) -> LedgerEntry:
        self.entries.append(entry)
        return entry

    def stale(self, today: date, window_days: int = 180) -> list[LedgerEntry]:
        return [e for e in self.entries if e.is_stale(today, window_days)]

    def assumptions(self) -> list[LedgerEntry]:
        return [e for e in self.entries if e.is_assumption]

    def to_dict(self) -> dict[str, Any]:
        return {
            "fy": self.fy,
            "entries": [e.to_dict() for e in self.entries],
            "count": len(self.entries),
        }


def entry_from_citation(
    label: str,
    value: Money,
    citation: Citation,
    rs: TaxRuleset,
    *,
    rule_id: str | None = None,
    is_assumption: bool = False,
) -> LedgerEntry:
    """Join a `Citation` to the rule pack that produced the figure.

    The citation knows the section; the rule pack knows when it was verified
    and which sources it was read from. Neither alone is enough to render a
    figure a user can check.
    """
    return LedgerEntry(
        label=label,
        value=value,
        fy=citation.fy or rs.fy,
        act=citation.act,
        verified_on=rs.verified_on,
        rule_id=rule_id,
        section=citation.section,
        legacy_section=citation.legacy_section,
        # A citation's own URL wins where it has one; otherwise the rule
        # pack's sources stand in. Written out rather than chained with
        # `and`/`or`, which ruff flagged and was right to — the precedence is
        # not obvious and this is a provenance path.
        source_urls=(
            (citation.source_url,) if citation.source_url else rs.sources
        ),
        note=citation.note,
        is_assumption=is_assumption,
    )


def ledger_from_trace(
    trace: Trace,
    fy: str,
    *,
    ruleset: TaxRuleset | None = None,
) -> Ledger:
    """Build a ledger from a computation's worksheet.

    Walks the trace so the ledger cannot disagree with the arithmetic: a figure
    appears in the ledger because a step produced it, not because someone
    remembered to register it. Steps without a citation are attributed to the
    rule pack itself, which is honest — the slab table has a verification date
    even where the step carries no section.
    """
    rs = ruleset or load_ruleset(fy)
    ledger = Ledger(fy=rs.fy)

    def walk(step: Step) -> None:
        if step.citation is not None:
            ledger.add(entry_from_citation(
                step.label, step.result, step.citation, rs,
            ))
        else:
            ledger.add(LedgerEntry(
                label=step.label,
                value=step.result,
                fy=rs.fy,
                act=rs.governing_act,
                verified_on=rs.verified_on,
                rule_id=f"fy_{rs.fy.replace('-', '_')}",
                source_urls=rs.sources,
                note=step.note,
            ))
        for child in step.children:
            walk(child)

    for step in trace.steps:
        walk(step)
    return ledger


__all__ = [
    "Ledger",
    "LedgerEntry",
    "UndatedFigure",
    "entry_from_citation",
    "ledger_from_trace",
]
