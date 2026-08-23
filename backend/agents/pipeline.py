"""Analyst → Reviewer → answer. AGT-008 + AGT-009 + AGT-011.

    draft ──► review ──┬─ clean ────────────► answer
                       ├─ amend/flag ───────► answer + verbatim caveats
                       └─ block ─► redraft ─► review ─┬─ clean ─► answer
                                                      └─ block ─► WITHHELD

Three independent checks with uncorrelated failure modes:

  1. `backend/core` computes every figure deterministically  (347 tests)
  2. `numeric_provenance` rejects any figure not in the tool results (mechanical)
  3. the Reviewer catches omission and framing, proving each challenge by
     calling the engine itself

Two language models marking each other's homework would give you one check, and
a misleading sense of two. The difference is that the Reviewer's authority is
the engine, not its own opinion about numbers.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from backend.agents.analyst import Analyst, AnalystRequest
from backend.agents.review_protocol import (
    Category,
    FinalAnswer,
    Finding,
    ReviewOutcome,
    Verdict,
    apply,
)
from backend.agents.reviewer_ca import CAReviewer, DraftUnderReview
from backend.agents.reviewer_risk import RiskReviewer

logger = logging.getLogger(__name__)

MAX_REDRAFTS = 1  # one retry, then fail visibly


@dataclass(slots=True)
class PipelineResult:
    answer: FinalAnswer
    drafts: list[str] = field(default_factory=list)
    reviews: list[ReviewOutcome] = field(default_factory=list)
    total_latency_ms: float = 0.0
    llm_calls: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer.to_dict(),
            "draft_count": len(self.drafts),
            "reviews": [r.to_dict() for r in self.reviews],
            "total_latency_ms": round(self.total_latency_ms, 1),
            "llm_calls": self.llm_calls,
        }


async def run(
    *,
    query: str,
    profile: dict[str, Any],
    fy: str,
    tool_results: list[dict[str, Any]],
    regime: str = "new",
    analyst: Analyst | None = None,
    reviewer: CAReviewer | None = None,
    risk_reviewer: RiskReviewer | None = None,
) -> PipelineResult:
    """Draft, review, and either serve, amend, or withhold.

    The risk pass runs after the CA pass and only where the answer asserts a
    claim — an informational answer skips it, which is what keeps the
    three-pass path inside its latency budget.
    """
    analyst = analyst or Analyst()
    reviewer = reviewer or CAReviewer()
    risk_reviewer = risk_reviewer if risk_reviewer is not None else RiskReviewer()

    started = time.perf_counter()
    result = PipelineResult(answer=FinalAnswer(text=""))
    revision_note = ""

    for attempt in range(MAX_REDRAFTS + 1):
        draft = await analyst.draft(
            AnalystRequest(
                query=query, profile=profile, fy=fy, regime=regime,
                tool_results=tool_results, revision_note=revision_note,
            )
        )
        result.llm_calls += 1

        if draft.error or not draft.text:
            # The analyst could not produce anything. Say so — do not fall
            # through to a partial or templated answer.
            result.answer = FinalAnswer(
                text=(
                    "We could not produce an answer just now. Nothing was "
                    "computed incorrectly; the explanation step failed."
                ),
                withheld=True,
                failure_reason=draft.error or "empty draft",
            )
            break

        result.drafts.append(draft.text)

        outcome = await reviewer.review(
            DraftUnderReview(
                query=query, draft=draft.text, profile=profile,
                tool_results=tool_results, fy=fy, regime=regime,
            )
        )
        # Third pass: assessment risk and scope. Skipped for informational
        # answers; scope is checked regardless because it can block.
        if not outcome.blocked:
            under_review = DraftUnderReview(
                query=query, draft=draft.text, profile=profile,
                tool_results=tool_results, fy=fy, regime=regime,
            )
            outcome.findings.extend(await risk_reviewer.review(under_review))
            outcome.findings.sort(key=lambda f: f.verdict.rank)

        result.reviews.append(outcome)

        final = apply(draft.text, outcome, already_redrafted=attempt > 0)

        if not final.withheld:
            result.answer = final
            break

        if attempt >= MAX_REDRAFTS:
            # Second block. `apply` has already produced the withheld message;
            # serving the draft here would make the review a delay, not a check.
            result.answer = final
            break

        revision_note = "; ".join(
            f.detail for f in outcome.findings if f.verdict.withholds_answer
        )
        logger.info("draft blocked, redrafting once: %s", revision_note)

    result.total_latency_ms = (time.perf_counter() - started) * 1000

    # PRD-004. Recorded here, at the one place every answer passes through,
    # rather than at each call site — the same argument as redacting at the
    # log formatter. A caller that forgets is a metric that undercounts
    # silently, and an undercounted withheld rate is worse than none.
    from backend.observability import metrics

    metrics.record_pipeline_result(result)

    return result


def summarise_for_evidence_pack(result: PipelineResult) -> dict[str, Any]:
    """Everything the review contributed, including findings that were resolved.

    A pack showing only the final answer would hide that a reviewer objected and
    the objection was fixed — which is exactly the part a reader checking the
    work would want to see.
    """
    all_findings: list[Finding] = [f for r in result.reviews for f in r.findings]
    return {
        "reviewed": True,
        "redrafted": result.answer.redrafted,
        "withheld": result.answer.withheld,
        "findings": [f.to_dict() for f in all_findings],
        "findings_by_category": {
            c.value: sum(1 for f in all_findings if f.category is c)
            for c in Category
            if any(f.category is c for f in all_findings)
        },
        "verdict_counts": {
            v.value: sum(1 for f in all_findings if f.verdict is v) for v in Verdict
        },
    }
