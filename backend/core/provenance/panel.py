"""The evidence and working panel — EVD-005.

One payload, four tabs, assembled from the deterministic engine:

    Working      the actual `Trace`, rendered as a worksheet
    Sources      every citation with its provision and last-checked date
    Assumptions  each labelled, each with the field it would edit
    Confidence   what the level is, and what would raise it, and by how much

Why the shape is built here and not in the UI
---------------------------------------------
A frontend that stitches trace + ledger + confidence itself will eventually
render a figure the trace does not contain — by rounding for display, by
re-deriving a total, by summarising a step. This module hands over exactly what
should appear, so the panel's job is layout only.

"Not a re-narration" is the acceptance criterion
------------------------------------------------
The Working tab shows `Trace.render()` — the same lines the Evidence Pack prints
and the same lines `replay()` verifies. It is not a prose account of what the
engine did. A re-narration can drift from the arithmetic; a rendering cannot,
because `verify()` fails if the steps no longer reproduce their own results.

Assumptions are editable, which means they must be addressable
--------------------------------------------------------------
An assumption the user can see but not correct is an irritation. Each carries
the profile field it maps to, so the panel can offer an input rather than a
sentence — and correcting one invalidates the computation rather than adjusting
the answer in place, which is why `edits_field` is a field name and not a value.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.core.provenance.confidence import Confidence
from backend.core.provenance.ledger import Ledger, ledger_from_trace
from backend.core.provenance.trace import Trace
from backend.core.rules.loader import TaxRuleset, load_ruleset


@dataclass(frozen=True, slots=True)
class AssumptionRow:
    """One assumption, and how to stop it being one."""

    what: str
    value: str
    edits_field: str
    gain_if_confirmed: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "what": self.what,
            "value": self.value,
            "edits_field": self.edits_field,
            "gain_if_confirmed": self.gain_if_confirmed,
            "is_assumption": True,
        }


@dataclass(slots=True)
class EvidencePanel:
    fy: str
    worksheets: list[Trace] = field(default_factory=list)
    ledger: Ledger | None = None
    confidence: Confidence | None = None
    assumptions: list[AssumptionRow] = field(default_factory=list)

    # ── the four tabs ───────────────────────────────────────────────────────

    def working(self) -> list[dict[str, Any]]:
        """The trace itself, line for line. Never a summary of it."""
        return [
            {
                "title": t.title,
                "lines": t.render().splitlines(),
                "result": str(t.result),
                # A worksheet that does not replay must not be presented as one.
                "replays": t.verify() == [],
            }
            for t in self.worksheets
        ]

    def sources(self) -> list[dict[str, Any]]:
        """Distinct provisions, each once, with what they decided.

        Deduplicated by citation: a slab table cited on six steps is one source,
        and listing it six times makes the tab look thorough while being harder
        to read.
        """
        seen: dict[str, dict[str, Any]] = {}
        for entry in (self.ledger.entries if self.ledger else ()):
            key = entry.citation_display
            if key not in seen:
                seen[key] = {
                    "citation": key,
                    "act": entry.act,
                    "section": entry.section,
                    "legacy_section": entry.legacy_section,
                    "both_numbering_schemes": entry.shows_both_numbering_schemes,
                    "verified_on": entry.verified_on.isoformat(),
                    "source_urls": list(entry.source_urls),
                    "note": entry.note or None,
                    "decided": [],
                }
            seen[key]["decided"].append(entry.label)
        return sorted(seen.values(), key=lambda s: s["citation"])

    def confidence_tab(self) -> dict[str, Any]:
        if self.confidence is None:
            return {
                "level": "unknown",
                "summary": "No confidence assessment was recorded for this result.",
                "improvements": [],
            }
        payload = self.confidence.to_dict()
        payload["what_would_raise_it"] = self.confidence.improvements_with_gain()
        return payload

    def assumptions_tab(self) -> list[dict[str, Any]]:
        return [a.to_dict() for a in self.assumptions]

    # ── output ──────────────────────────────────────────────────────────────

    @property
    def has_unreplayable_worksheet(self) -> bool:
        return any(not w["replays"] for w in self.working())

    def to_dict(self) -> dict[str, Any]:
        return {
            "fy": self.fy,
            "tabs": {
                "working": self.working(),
                "sources": self.sources(),
                "assumptions": self.assumptions_tab(),
                "confidence": self.confidence_tab(),
            },
            "counts": {
                "worksheets": len(self.worksheets),
                "sources": len(self.sources()),
                "assumptions": len(self.assumptions),
            },
            "has_unreplayable_worksheet": self.has_unreplayable_worksheet,
        }


def _assumption_rows(confidence: Confidence | None) -> list[AssumptionRow]:
    """Lift assumption signals into editable rows.

    `edits_field` is derived from the signal's own subject rather than parsed out
    of prose, so the panel offers an input bound to the right field. Guessing the
    field from a rendered sentence is how an "edit" writes to the wrong place.
    """
    if confidence is None:
        return []
    rows: list[AssumptionRow] = []
    for signal in confidence.signals:
        if signal.kind != "assumption":
            continue
        # Signal detail is "<what> = <value>" or "<what>: <value>".
        detail = signal.detail.removeprefix("assumed ")
        separator = " = " if " = " in detail else ": "
        what, _, value = detail.partition(separator)
        rows.append(AssumptionRow(
            what=what.strip(),
            value=value.strip(),
            edits_field=what.strip().replace(" ", "_").lower(),
            gain_if_confirmed=str(signal.penalty),
        ))
    return rows


def build_panel(
    result: Any,
    fy: str,
    *,
    extra_worksheets: list[Trace] | None = None,
    ruleset: TaxRuleset | None = None,
) -> EvidencePanel:
    """Assemble a panel from a computation result.

    Takes the whole result rather than its parts so the four tabs cannot be
    built from different runs — which is how a panel ends up showing a worksheet
    for one computation next to a confidence score for another.
    """
    rs = ruleset or load_ruleset(fy)
    worksheets = [result.trace, *(extra_worksheets or [])]

    ledger = Ledger(fy=rs.fy)
    for trace in worksheets:
        for entry in ledger_from_trace(trace, rs.fy, ruleset=rs).entries:
            ledger.add(entry)

    confidence = getattr(result, "confidence", None)
    return EvidencePanel(
        fy=rs.fy,
        worksheets=worksheets,
        ledger=ledger,
        confidence=confidence,
        assumptions=_assumption_rows(confidence),
    )


__all__ = ["AssumptionRow", "EvidencePanel", "build_panel"]
