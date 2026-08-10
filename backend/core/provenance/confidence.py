"""Composed confidence — EVD-002.

What v1 does
------------
    confidence=0.80   # hardcoded literal in deduction_hunter.py
    confidence=0.88   # hardcoded literal in price_intelligence.py

and `ValidationReport.add_warning` subtracts a flat 0.1 regardless of what the
warning said. Those numbers are then rendered to users as a quality score.
Inventing a measurement is worse than offering none, because it spends trust
the system has not earned.

The honest model
----------------
For a deterministic engine, the arithmetic is certain. All the uncertainty
lives in the inputs. So confidence is not a property of the answer — it is a
property of what went into it, composed from five measurable signals:

    input provenance   official document > parsed > user-stated > assumed
    rule freshness     how long since a human verified the rule pack
    completeness       which relevant fields are missing
    assumptions        how many defaults were substituted for real data
    source tier        official vs commercial vs aggregator (procurement)

Two consequences worth stating plainly:

  * Complete official inputs against a fresh rule pack report CERTAIN, not 87%.
    Fake precision is itself a trust leak.
  * Every reduction names its cause and what would undo it, so the score is
    actionable rather than decorative.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any


class Provenance(str, Enum):  # noqa: UP042
    """Where a single input value came from. Ordered best to worst."""

    OFFICIAL_DOCUMENT = "official_document"   # Form 16, AIS, broker statement
    VERIFIED_PARSE = "verified_parse"         # parsed and confirmed by the user
    PARSED = "parsed"                         # parsed, not yet confirmed
    USER_STATED = "user_stated"               # typed in
    DEFAULT = "default"                       # a rule-pack default
    ASSUMED = "assumed"                       # we guessed

    @property
    def penalty(self) -> Decimal:
        return _PROVENANCE_PENALTY[self]

    @property
    def label(self) -> str:
        return self.value.replace("_", " ")


_PROVENANCE_PENALTY: dict[Provenance, Decimal] = {
    Provenance.OFFICIAL_DOCUMENT: Decimal("0.00"),
    Provenance.VERIFIED_PARSE: Decimal("0.00"),
    Provenance.PARSED: Decimal("0.05"),
    Provenance.USER_STATED: Decimal("0.05"),
    Provenance.DEFAULT: Decimal("0.15"),
    Provenance.ASSUMED: Decimal("0.25"),
}


class Level(str, Enum):  # noqa: UP042
    """What we tell the user. Deliberately words, not a percentage.

    A number invites false precision — nobody can defend 87% versus 84%. The
    band plus its reasons is both more honest and more useful.
    """

    CERTAIN = "certain"
    HIGH = "high"
    PARTIAL = "partial"
    LOW = "low"
    INSUFFICIENT = "insufficient"

    @property
    def display(self) -> str:
        return {
            Level.CERTAIN: "Certain",
            Level.HIGH: "High confidence",
            Level.PARTIAL: "Partial confidence",
            Level.LOW: "Low confidence",
            Level.INSUFFICIENT: "Not enough information",
        }[self]


@dataclass(frozen=True, slots=True)
class Signal:
    """One thing that reduced confidence, and how to undo it."""

    kind: str
    detail: str
    penalty: Decimal
    remedy: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "detail": self.detail,
            "penalty": str(self.penalty),
            "remedy": self.remedy or None,
        }


@dataclass(slots=True)
class Confidence:
    """A confidence assessment that can explain itself."""

    signals: list[Signal] = field(default_factory=list)
    blocking: list[str] = field(default_factory=list)
    deterministic: bool = True

    # ── recording ───────────────────────────────────────────────────────────

    def input_from(self, field_name: str, provenance: Provenance) -> None:
        penalty = provenance.penalty
        if penalty == 0:
            return
        remedy = {
            Provenance.PARSED: f"confirm the parsed value of {field_name}",
            Provenance.USER_STATED: f"upload the source document for {field_name}",
            Provenance.DEFAULT: f"provide your actual {field_name}",
            Provenance.ASSUMED: f"provide your actual {field_name}",
        }.get(provenance, "")
        self.signals.append(
            Signal("input_provenance", f"{field_name}: {provenance.label}",
                   penalty, remedy)
        )

    def rule_age(self, fy: str, verified_on: date, today: date, limit_days: int = 180) -> None:
        age = (today - verified_on).days
        if age <= limit_days // 2:
            return
        penalty = Decimal("0.05") if age <= limit_days else Decimal("0.20")
        self.signals.append(
            Signal(
                "rule_freshness",
                f"FY {fy} rules last verified {age} days ago",
                penalty,
                "re-verify the rule pack against incometax.gov.in",
            )
        )

    def missing(self, field_name: str, consequence: str, *, blocks: bool = False) -> None:
        """A field we did not get, and what it cost.

        `blocks=True` means the answer cannot be computed at all — that is
        INSUFFICIENT, not a low score, and must never be presented as a number.
        """
        if blocks:
            self.blocking.append(f"{field_name} — {consequence}")
            return
        self.signals.append(
            Signal("incomplete", f"{field_name} not provided — {consequence}",
                   Decimal("0.10"), f"provide {field_name}")
        )

    def assumption(self, what: str, value: str) -> None:
        self.signals.append(
            Signal("assumption", f"assumed {what} = {value}", Decimal("0.10"),
                   f"confirm or correct {what}")
        )

    def source_tier(self, what: str, tier: int) -> None:
        if tier <= 1:
            return
        penalty = Decimal("0.05") if tier == 2 else Decimal("0.25")
        self.signals.append(
            Signal(
                "source_tier",
                f"{what} from a tier-{tier} source"
                + (" (not official)" if tier == 3 else " (manufacturer-stated)"),
                penalty,
                "confirm against the official portal" if tier == 3 else "",
            )
        )

    def llm_generated(self, what: str) -> None:
        """Should never fire in the core. If it does, something upstream let a
        model touch a figure, and the answer is not deterministic."""
        self.deterministic = False
        self.signals.append(
            Signal("llm_generated", f"{what} originated from a language model",
                   Decimal("0.50"), "this value must be computed, not generated")
        )

    # ── result ──────────────────────────────────────────────────────────────

    @property
    def score(self) -> Decimal:
        total = Decimal("1.00")
        for s in self.signals:
            total -= s.penalty
        return max(Decimal("0.00"), min(Decimal("1.00"), total))

    @property
    def level(self) -> Level:
        if self.blocking:
            return Level.INSUFFICIENT
        if not self.signals and self.deterministic:
            # Nothing reduced it: complete official inputs, fresh rules,
            # deterministic arithmetic. Say so plainly.
            return Level.CERTAIN
        s = self.score
        if s >= Decimal("0.90"):
            return Level.HIGH
        if s >= Decimal("0.65"):
            return Level.PARTIAL
        return Level.LOW

    @property
    def summary(self) -> str:
        if self.blocking:
            return "Not enough information to compute this reliably."
        if self.level is Level.CERTAIN:
            return (
                "Computed from complete, official inputs against verified "
                "rules. This figure is exact."
            )
        top = max(self.signals, key=lambda s: s.penalty)
        return f"{self.level.display} — mainly because {top.detail}."

    def improvements(self) -> list[str]:
        """Concretely, what would raise this — ordered by how much."""
        return [
            s.remedy
            for s in sorted(self.signals, key=lambda x: x.penalty, reverse=True)
            if s.remedy
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level.value,
            "display": self.level.display,
            "score": str(self.score),
            "is_certain": self.level is Level.CERTAIN,
            "deterministic": self.deterministic,
            "summary": self.summary,
            "signals": [s.to_dict() for s in self.signals],
            "blocking": self.blocking,
            "improvements": self.improvements(),
        }

