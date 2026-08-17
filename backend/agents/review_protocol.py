"""Graded review verdicts — AGT-011.

The Reviewer can stop an answer reaching the user. It can never change a number
in one. That asymmetry is the whole design:

  * If the Reviewer could edit figures, an LLM would once again be deciding what
    a taxpayer owes — the exact thing `backend/core` exists to prevent.
  * If it could only annotate, a genuinely wrong answer would still ship with a
    footnote.

So findings are graded, and each grade has a mechanical consequence:

    BLOCK   the answer is withheld and the Analyst redrafts, ONCE. A second
            BLOCK surfaces an explicit failure rather than quietly serving the
            unreviewed draft.
    AMEND   the Reviewer's text is appended VERBATIM. The Analyst does not get
            to paraphrase an inconvenient caveat into something softer.
    FLAG    the answer is shown with a visible note attached.

Nothing is ever silently rewritten. If the two agents disagreed, the user sees
that they disagreed — a rewrite that hides the disagreement defeats the point of
having a reviewer at all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Verdict(str, Enum):
    BLOCK = "block"
    AMEND = "amend"
    FLAG = "flag"

    @property
    def withholds_answer(self) -> bool:
        return self is Verdict.BLOCK

    @property
    def rank(self) -> int:
        return {Verdict.BLOCK: 0, Verdict.AMEND: 1, Verdict.FLAG: 2}[self]


class Category(str, Enum):
    """What kind of problem this is. Recorded so the eval corpus can assert on
    the class of failure caught, not just that something was caught."""

    FABRICATED_FIGURE = "fabricated_figure"
    OMITTED_OPTION = "omitted_option"          # a better regime nobody mentioned
    DROPPED_WINDOW = "dropped_window"          # closed benefit silently omitted
    MISLEADING_FRAMING = "misleading_framing"  # right number, wrong impression
    INVALID_CITATION = "invalid_citation"
    OUT_OF_SCOPE = "out_of_scope"              # SEBI-regulated advice
    UNASKED_QUESTION = "unasked_question"
    DOCUMENTATION_RISK = "documentation_risk"  # from the AO pass


@dataclass(frozen=True, slots=True)
class Finding:
    """One reviewer objection.

    `evidence` is the engine call that substantiates it. A finding without
    evidence is an opinion, and `ReviewOutcome.validate` rejects it for the
    grades where that matters.
    """

    verdict: Verdict
    category: Category
    detail: str
    evidence: dict[str, Any] | None = None
    amendment: str = ""
    reviewer: str = "ca"

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "category": self.category.value,
            "detail": self.detail,
            "evidence": self.evidence,
            "amendment": self.amendment or None,
            "reviewer": self.reviewer,
        }


class ProtocolViolation(RuntimeError):
    """The review pipeline was asked to do something it must never do."""


@dataclass(slots=True)
class ReviewOutcome:
    findings: list[Finding] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return any(f.verdict.withholds_answer for f in self.findings)

    @property
    def amendments(self) -> list[Finding]:
        return [f for f in self.findings if f.verdict is Verdict.AMEND]

    @property
    def flags(self) -> list[Finding]:
        return [f for f in self.findings if f.verdict is Verdict.FLAG]

    def validate(self) -> None:
        """A BLOCK or AMEND must be substantiated.

        Blocking an answer or forcing text into it on an unevidenced hunch is
        how a reviewer becomes noise that people learn to route around.
        """
        for f in self.findings:
            if f.verdict in (Verdict.BLOCK, Verdict.AMEND) and not f.evidence:
                raise ProtocolViolation(
                    f"{f.verdict.value} finding '{f.detail[:60]}' has no evidence. "
                    f"A reviewer may only block or amend on something it verified "
                    f"against the engine."
                )
            if f.verdict is Verdict.AMEND and not f.amendment.strip():
                raise ProtocolViolation(
                    f"AMEND finding '{f.detail[:60]}' carries no amendment text."
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "blocked": self.blocked,
            "findings": [f.to_dict() for f in self.findings],
        }


# ── figure integrity ────────────────────────────────────────────────────────

_FIGURE = re.compile(r"(?:₹|Rs\.?|INR)\s*\d[\d,]*(?:\.\d+)?", re.IGNORECASE)


def figures_in(text: str) -> list[str]:
    """Currency-marked amounts, normalised for comparison."""
    return sorted(re.sub(r"[₹,\s]|Rs\.?|INR", "", m, flags=re.IGNORECASE)
                  for m in _FIGURE.findall(text))


def assert_figures_unchanged(before: str, after: str) -> None:
    """The invariant that makes the Reviewer safe to run at all.

    Applied after every amendment. If the set of currency amounts differs, some
    step in the pipeline altered a number, and the pipeline fails loudly rather
    than serving a figure the engine did not produce.
    """
    original, result = figures_in(before), figures_in(after)
    # Amendments may ADD figures — a reviewer noting "the old regime is ₹40,120
    # cheaper" is adding an engine-verified number. It may never remove or
    # change one.
    missing = [f for f in original if f not in result]
    if missing:
        raise ProtocolViolation(
            f"review altered or removed figures {missing}. A verdict may block "
            f"or annotate an answer; it may never change what the engine computed."
        )


# ── applying the outcome ────────────────────────────────────────────────────

@dataclass(slots=True)
class FinalAnswer:
    text: str
    withheld: bool = False
    failure_reason: str = ""
    notes: list[str] = field(default_factory=list)
    review: ReviewOutcome | None = None
    redrafted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "withheld": self.withheld,
            "failure_reason": self.failure_reason or None,
            "notes": self.notes,
            "redrafted": self.redrafted,
            "review": self.review.to_dict() if self.review else None,
        }


WITHHELD_MESSAGE = (
    "This answer was withheld. Our reviewer found a problem the analyst could "
    "not resolve, and showing you a figure we do not stand behind would be "
    "worse than showing you nothing."
)


def apply(
    draft: str,
    outcome: ReviewOutcome,
    *,
    already_redrafted: bool = False,
) -> FinalAnswer:
    """Turn a draft plus review findings into what the user actually sees."""
    outcome.validate()

    if outcome.blocked:
        if already_redrafted:
            # Second block. Fail visibly. Serving the unreviewed draft here
            # would mean the review's only effect was to delay a bad answer.
            reasons = "; ".join(
                f.detail for f in outcome.findings if f.verdict.withholds_answer
            )
            return FinalAnswer(
                text=WITHHELD_MESSAGE,
                withheld=True,
                failure_reason=reasons,
                review=outcome,
                redrafted=True,
            )
        # First block — caller redrafts.
        return FinalAnswer(
            text="", withheld=True,
            failure_reason="redraft required", review=outcome,
        )

    text = draft
    for f in outcome.amendments:
        # Verbatim. The Analyst never gets to re-word this.
        text = f"{text.rstrip()}\n\n{f.amendment.strip()}"

    assert_figures_unchanged(draft, text)

    return FinalAnswer(
        text=text,
        notes=[f.detail for f in outcome.flags],
        review=outcome,
        redrafted=already_redrafted,
    )
