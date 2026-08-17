"""The Evidence Pack — EVD-006.

What it is for
--------------
A document someone can hand to their CA, or keep for an assessment three years
from now, that answers every question an assessing officer might ask: what you
told us, what we assumed, what rule we applied, when that rule was last checked
against a source, and the arithmetic in full.

The rule that shapes the whole design
-------------------------------------
**No figure in the pack may originate from a language model.** Not "we try not
to" — the pack is assembled exclusively from `Trace` steps and `LedgerEntry`
objects, both of which come out of the deterministic engine. There is no code
path by which prose reaches a number field. `numeric_provenance` can be run over
the rendered pack and must find nothing, and `backend/core/tests/test_evidence_pack.py`
does exactly that.

Why the content model is separate from the PDF
----------------------------------------------
This module builds a `PackContent` — pure data, no I/O, no rendering. The PDF
writer lives at the boundary (`backend/services/evidence_pack_pdf.py`) because
reportlab is I/O and core is forbidden it. The separation also means the same
content renders to the machine-readable appendix and to the page, from one
source, so the two cannot disagree.

Closed windows are content, not an error
----------------------------------------
A benefit that expired before the user could claim it belongs in the pack with
its closing date. "You could have had ₹1,50,000 under s.80EEB but the window
for loan sanction closed on 31 March 2023" is the single most useful sentence
this product can produce for someone who is about to buy an electric car
believing otherwise.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from backend.core.provenance.confidence import Confidence
from backend.core.provenance.ledger import Ledger, LedgerEntry, ledger_from_trace
from backend.core.provenance.money import Money
from backend.core.provenance.trace import Trace
from backend.core.rules.loader import TaxRuleset, load_ruleset

PACK_FORMAT_VERSION = "1"


@dataclass(frozen=True, slots=True)
class InputRecord:
    """One thing the user told us, or one thing we assumed for them.

    The distinction is the point. An assumption presented as a stated fact is
    how a pack becomes evidence for a figure nobody actually agreed to.
    """

    label: str
    value: str
    provenance: str            # "user stated", "Form 16", "assumed", ...
    is_assumption: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "value": self.value,
            "provenance": self.provenance,
            "is_assumption": self.is_assumption,
        }


@dataclass(frozen=True, slots=True)
class ClosedWindow:
    """A benefit that no longer exists, and when it stopped."""

    name: str
    closed_on: date | None
    would_have_been_worth: Money
    reason: str = ""
    legacy_section: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "closed_on": self.closed_on.isoformat() if self.closed_on else None,
            "would_have_been_worth": self.would_have_been_worth.to_json(),
            "reason": self.reason,
            "section": self.legacy_section,
        }


@dataclass(slots=True)
class PackContent:
    """Everything the pack contains, as data. No rendering, no I/O."""

    title: str
    fy: str
    assessment_year: str
    governing_act: str
    generated_on: date
    rule_pack_verified_on: date
    rule_pack_sources: tuple[str, ...]
    # The pack file's fingerprint, not just its self-declared date. See
    # `TaxRuleset.content_hash` — a date is a claim, a hash is a fact.
    rule_pack_version: str = ""

    inputs: list[InputRecord] = field(default_factory=list)
    worksheets: list[Trace] = field(default_factory=list)
    ledger: Ledger | None = None
    closed_windows: list[ClosedWindow] = field(default_factory=list)
    confidence: Confidence | None = None
    notes: list[str] = field(default_factory=list)

    # ── the properties that make the pack auditable ─────────────────────────

    @property
    def assumptions(self) -> list[InputRecord]:
        return [i for i in self.inputs if i.is_assumption]

    @property
    def rule_pack_id(self) -> str:
        return f"fy_{self.fy.replace('-', '_')}"

    def figures(self) -> list[LedgerEntry]:
        return list(self.ledger.entries) if self.ledger else []

    def input_hash(self) -> str:
        """A hash of the stated facts, so a regeneration can be shown to have
        used the same inputs. EVD-007 builds on this."""
        payload = json.dumps(
            [i.to_dict() for i in self.inputs], sort_keys=True, ensure_ascii=False
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def content_hash(self) -> str:
        """A hash over everything that determines the computation section.

        Deliberately excludes `generated_on` — the same inputs under the same
        rule pack must hash identically whether run today or next week, or the
        hash cannot be used to prove reproducibility.
        """
        payload = json.dumps(
            {
                "format": PACK_FORMAT_VERSION,
                "fy": self.fy,
                "rule_pack_verified_on": self.rule_pack_verified_on.isoformat(),
                "inputs": [i.to_dict() for i in self.inputs],
                "worksheets": [t.to_dict() for t in self.worksheets],
                "closed_windows": [w.to_dict() for w in self.closed_windows],
            },
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def appendix(self) -> dict[str, Any]:
        """The machine-readable appendix embedded in the pack.

        Someone should be able to re-run the computation from this alone. That
        is the difference between a document that asserts a number and one that
        lets you check it.
        """
        return {
            "pack_format_version": PACK_FORMAT_VERSION,
            "fy": self.fy,
            "assessment_year": self.assessment_year,
            "governing_act": self.governing_act,
            "rule_pack_id": self.rule_pack_id,
            "rule_pack_version": self.rule_pack_version,
            "rule_pack_verified_on": self.rule_pack_verified_on.isoformat(),
            "rule_pack_sources": list(self.rule_pack_sources),
            "generated_on": self.generated_on.isoformat(),
            "input_hash": self.input_hash(),
            "content_hash": self.content_hash(),
            "inputs": [i.to_dict() for i in self.inputs],
            "worksheets": [t.to_dict() for t in self.worksheets],
            "ledger": self.ledger.to_dict() if self.ledger else None,
            "closed_windows": [w.to_dict() for w in self.closed_windows],
            "confidence": self.confidence.to_dict() if self.confidence else None,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            **self.appendix(),
            "notes": self.notes,
        }


def build_pack(
    title: str,
    fy: str,
    *,
    worksheets: list[Trace],
    inputs: list[InputRecord] | None = None,
    closed_windows: list[ClosedWindow] | None = None,
    confidence: Confidence | None = None,
    notes: list[str] | None = None,
    generated_on: date,
    ruleset: TaxRuleset | None = None,
) -> PackContent:
    """Assemble a pack from traces and stated facts.

    `worksheets` is the only source of figures. Prose can be passed in `notes`
    and never carries a number the pack asserts — which is what makes the
    no-LLM-figures guarantee mechanical rather than aspirational.
    """
    rs = ruleset or load_ruleset(fy)

    ledger = Ledger(fy=rs.fy)
    for trace in worksheets:
        for entry in ledger_from_trace(trace, rs.fy, ruleset=rs).entries:
            ledger.add(entry)

    return PackContent(
        title=title,
        fy=rs.fy,
        assessment_year=rs.assessment_year,
        governing_act=rs.governing_act,
        generated_on=generated_on,
        rule_pack_verified_on=rs.verified_on,
        rule_pack_sources=rs.sources,
        rule_pack_version=rs.version,
        inputs=list(inputs or []),
        worksheets=list(worksheets),
        ledger=ledger,
        closed_windows=list(closed_windows or []),
        confidence=confidence,
        notes=list(notes or []),
    )


def closed_windows_from_outcomes(outcomes: list[Any]) -> list[ClosedWindow]:
    """Lift WINDOW_CLOSED eligibility outcomes into pack content.

    Only the closed ones. An eligible benefit belongs in the recommendation; a
    closed one belongs in the pack, because it is the thing the user is most
    likely to be wrong about and least likely to be told.
    """
    out: list[ClosedWindow] = []
    for o in outcomes:
        if getattr(o.status, "value", None) != "window_closed":
            continue
        out.append(ClosedWindow(
            name=o.name,
            closed_on=o.closed_on,
            would_have_been_worth=o.max_benefit,
            reason=o.reason,
            legacy_section=(
                o.citation.legacy_section if getattr(o, "citation", None) else None
            ),
        ))
    return out


__all__ = [
    "PACK_FORMAT_VERSION",
    "ClosedWindow",
    "InputRecord",
    "PackContent",
    "build_pack",
    "closed_windows_from_outcomes",
]
