"""The pipeline actually feeds the metrics — PRD-004.

Every metric in this project's history that mattered was one nobody had wired
up. A `record_pipeline_result` that is never called produces a dashboard of
flat zeroes, which reads as "nothing is going wrong" rather than as "nothing
is being measured" — the more dangerous of the two.

So this asserts the wiring end to end, through `pipeline.run`, with stub
agents and no network. The stubs are deliberately different from each other:
the CA reviewer returns a `ReviewOutcome`, the risk reviewer returns a LIST of
findings, and a shared stub would hide that the pipeline treats them
differently.
"""

from __future__ import annotations

import pytest

from backend.agents import pipeline
from backend.agents.analyst import AnalystDraft
from backend.agents.review_protocol import (
    Category,
    Finding,
    ReviewOutcome,
    Verdict,
)
from backend.observability import metrics

TOOL_RESULTS = [{
    "tool": "compute_tax",
    "success": True,
    "result": {"total_tax": "0.00", "taxable": "1200000.00"},
}]


def _value(counter, **labels) -> float:
    return counter.labels(**labels)._value.get()


class _Analyst:
    def __init__(self, text: str = "Your tax for FY 2026-27 is Rs 0.00."):
        self.text = text

    async def draft(self, request):
        return AnalystDraft(text=self.text, tool_results=request.tool_results)


class _Reviewer:
    def __init__(self, findings=()):
        self.findings = list(findings)

    async def review(self, draft):
        return ReviewOutcome(findings=list(self.findings))


class _RiskReviewer:
    async def review(self, draft):
        return []  # a list, not a ReviewOutcome


async def _run(analyst=None, reviewer=None):
    return await pipeline.run(
        query="What is my tax?",
        profile={"salary": 1200000},
        fy="2026-27",
        tool_results=TOOL_RESULTS,
        analyst=analyst or _Analyst(),
        reviewer=reviewer or _Reviewer(),
        risk_reviewer=_RiskReviewer(),
    )


@pytest.mark.asyncio
async def test_a_clean_answer_increments_served():
    before = _value(metrics.answers, outcome="served")
    result = await _run()
    assert not result.answer.withheld
    assert _value(metrics.answers, outcome="served") == before + 1


@pytest.mark.asyncio
async def test_a_blocked_answer_increments_withheld_and_redrafts():
    """The number an operator most needs and least had.

    A rising withheld rate means the analyst has started producing answers the
    reviewer will not stand behind. Nothing anywhere reported it before this.
    """
    blocking = Finding(
        verdict=Verdict.BLOCK,
        category=Category.FABRICATED_FIGURE,
        detail="a figure appeared that no tool produced",
        evidence={"tool": "compute_tax", "expected": "0.00"},
    )
    withheld_before = _value(metrics.answers, outcome="withheld")
    findings_before = _value(
        metrics.review_findings,
        verdict="block", category="fabricated_figure", reviewer="ca",
    )
    redrafts_before = metrics.redrafts._value.get()

    result = await _run(reviewer=_Reviewer([blocking]))

    assert result.answer.withheld
    assert _value(metrics.answers, outcome="withheld") == withheld_before + 1
    # Both review passes are recorded — the original block AND the block on
    # the redraft. Recording only the final one would understate how often the
    # reviewer is intervening.
    assert _value(
        metrics.review_findings,
        verdict="block", category="fabricated_figure", reviewer="ca",
    ) == findings_before + 2
    assert metrics.redrafts._value.get() > redrafts_before


@pytest.mark.asyncio
async def test_llm_calls_and_latency_are_observed():
    calls_before = metrics.llm_calls._value.get()
    latency_before = metrics.pipeline_latency._sum.get()

    await _run()

    assert metrics.llm_calls._value.get() == calls_before + 1
    # A histogram whose sum never moves is a histogram nobody is filling.
    assert metrics.pipeline_latency._sum.get() > latency_before


@pytest.mark.asyncio
async def test_an_analyst_failure_is_counted_as_withheld_not_dropped():
    """The path that produces no draft at all.

    It exits the loop early, so it is the one most likely to skip the
    recording — and an unexplained drop in total answers is much harder to
    diagnose than a visible spike in withheld ones.
    """
    class _Failing:
        async def draft(self, request):
            return AnalystDraft(text="", tool_results=[], error="model timeout")

    before = _value(metrics.answers, outcome="withheld")
    result = await _run(analyst=_Failing())

    assert result.answer.withheld
    assert _value(metrics.answers, outcome="withheld") == before + 1
