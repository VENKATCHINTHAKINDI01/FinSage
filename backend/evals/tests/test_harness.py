"""Tests for the harness itself.

A test harness nobody tests is a harness that quietly stops working. The
numeric_provenance gate in particular is the single control standing between a
language model and a rupee figure on a user's screen — if it silently degrades
into a pass-everything function, nothing downstream will notice.

That is not hypothetical: the first draft of the section-reference regex made
the section prefix optional, which generalised "80C" into "any two-digit
number" and masked a fabricated ₹46,800 as a statutory reference. The suite
passed. `test_catches_injected_hallucination` is the regression test for that.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.evals import runner
from backend.evals.scorers.numeric_provenance import (
    NumericProvenanceScorer,
    extract_claimed_numbers,
)
from backend.evals.types import AgentInvocation, Verdict

SCORER = NumericProvenanceScorer()

GROUNDING = [
    {
        "tool": "compute_tax",
        "success": True,
        "result": {"taxable_income": 1200000, "rebate_87a": 60000, "total_tax": 0},
    }
]


def _invoke(text: str, tool_results=None, profile=None) -> AgentInvocation:
    return AgentInvocation(
        agent="test",
        query="q",
        profile=profile or {},
        tool_results=GROUNDING if tool_results is None else tool_results,
        output_text=text,
    )


# ── The regression that matters ─────────────────────────────────────────────

def test_catches_injected_hallucination() -> None:
    """A figure absent from every tool result must fail the gate."""
    score = SCORER.score({}, _invoke(
        "Your taxable income is ₹12,00,000 and your total tax is ₹0. "
        "You will also save ₹46,800 through additional planning."
    ))
    assert score.verdict is Verdict.FAIL
    assert any("46,800" in e for e in score.evidence)


def test_section_references_are_not_mistaken_for_money() -> None:
    """The bug that let ₹46,800 through: section patterns must not generalise
    to bare two-digit numbers."""
    claimed = [v for v, _ in extract_claimed_numbers(
        "Under section 80C and 80CCD(1B), with 87A rebate and 24(b) interest, "
        "ITR-1 applies for FY 2026-27."
    )]
    assert claimed == [], f"structural references leaked as money: {claimed}"


def test_hallucinated_fixture_fails_end_to_end() -> None:
    """The recorded 'bad agent' fixture must fail through the real runner."""
    invocation = runner.load_fixture("EV-80EEB-HALLUCINATED")
    assert invocation is not None, "negative-control fixture is missing"

    result = runner.run_scenario({"id": "EV-80EEB-HALLUCINATED"}, live=False)
    assert result.verdict is Verdict.FAIL

    failing = {s.scorer for s in result.failures}
    assert "numeric_provenance" in failing


def test_grounded_fixture_passes_end_to_end() -> None:
    result = runner.run_scenario({"id": "EV-80EEB-CLOSED-WINDOW"}, live=False)
    assert result.verdict is Verdict.PASS, [
        (s.scorer, s.detail) for s in result.failures
    ]


# ── Extraction behaviour ────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "text,expected",
    [
        ("₹1,25,000 exemption", [Decimal(125000)]),          # Indian grouping
        ("Rs 60,000 rebate", [Decimal(60000)]),
        ("about ₹12.75 lakh", [Decimal("1275000")]),          # lakh shorthand
        ("₹1.5 crore property", [Decimal("15000000")]),
        ("3 deductions apply", []),                           # small count
        ("taxed at 20%", []),                                 # bare rate
        ("valid for FY 2026-27", []),                         # financial year
        ("on 31 March 2023", []),                             # date
        ("use ITR-2 this year", []),                          # form number
    ],
)
def test_extraction(text: str, expected: list[Decimal]) -> None:
    assert [v for v, _ in extract_claimed_numbers(text)] == expected


def test_rounded_restatement_is_allowed() -> None:
    """'about ₹60,000' against a computed ₹60,432 is honest summarising."""
    score = SCORER.score({}, _invoke(
        "Your tax works out to about ₹60,000.",
        tool_results=[{"result": {"total_tax": 60432}}],
    ))
    assert score.verdict is Verdict.PASS


def test_precise_fabrication_is_not_allowed() -> None:
    """A precise figure near a real one is still fabricated, not rounded."""
    score = SCORER.score({}, _invoke(
        "Your tax works out to exactly ₹62,317.",
        tool_results=[{"result": {"total_tax": 60432}}],
    ))
    assert score.verdict is Verdict.FAIL


def test_user_supplied_figures_may_be_quoted_back() -> None:
    score = SCORER.score({}, _invoke(
        "On your salary of ₹18,00,000 the total tax is ₹0.",
        profile={"salary": 1800000},
    ))
    assert score.verdict is Verdict.PASS


def test_agent_error_skips_rather_than_passes() -> None:
    """A run that could not happen must never read as approval."""
    inv = _invoke("")
    inv.error = "timeout"
    assert SCORER.score({}, inv).verdict is Verdict.SKIP


# ── Runner plumbing ─────────────────────────────────────────────────────────

def test_eval_runner_replays_offline() -> None:
    outcome = runner.run(live=False)
    assert outcome.mode == "replay"
    assert outcome.results, "no scenarios discovered"
    assert all(r.scenario_id for r in outcome.results)


def test_summary_is_stable_for_baseline_diffing() -> None:
    """Two runs of identical input must produce identical summaries, or the
    baseline gate would fire on noise."""
    assert runner.run(live=False).summary() == runner.run(live=False).summary()


def test_regressions_ignores_newly_added_scenarios() -> None:
    """New scenarios failing is work in progress, not a regression."""
    outcome = runner.run(live=False)
    baseline = {"scenarios": {}}
    assert runner.regressions(outcome, baseline) == []


def test_regressions_flags_a_scenario_that_stopped_passing() -> None:
    outcome = runner.run(live=False)
    baseline = {"scenarios": {"GHOST-SCENARIO": {"verdict": "pass", "scorers": {}}}}
    regs = runner.regressions(outcome, baseline)
    assert any("GHOST-SCENARIO" in r for r in regs)


def test_the_live_path_runs_the_real_pipeline_with_a_stub_model() -> None:
    """AGT-005. `run_scenario(live=True)` used to raise NotImplementedError,
    which is why ten of fifteen scenarios had no fixture — each one needed
    bespoke code to produce tool results.

    The stubs are the point of this test: without them the only way to know
    the wiring works is to spend money on a live call and find out. Everything
    below the model is real — real scenario, real deterministic tool results
    from `backend.evals.toolcalls`, real review protocol.
    """
    scenario = {
        "id": "LIVE-PATH-SMOKE",
        "query": "What is my tax?",
        "profile": {"fy": "2026-27", "regime": "new", "salary": 1275000},
    }

    class StubAnalyst:
        async def draft(self, request):
            from backend.agents.analyst import AnalystDraft

            total = request.tool_results[0]["result"]["total_tax"]
            return AnalystDraft(
                text=f"Your tax for FY {request.fy} is Rs {total}.",
                tool_results=request.tool_results,
            )

    class StubReviewer:
        async def review(self, draft):
            from backend.agents.review_protocol import ReviewOutcome

            return ReviewOutcome(findings=[])

    class StubRiskReviewer:
        # Returns a LIST of findings, not a ReviewOutcome — the pipeline
        # extends `outcome.findings` with it. The two reviewer roles have
        # different contracts and a shared stub hides that.
        async def review(self, draft):
            return []

    invocation = runner.invoke_live(
        scenario, analyst=StubAnalyst(), reviewer=StubReviewer(),
        risk_reviewer=StubRiskReviewer(),
    )

    assert invocation.agent == "analyst_reviewer_pipeline"
    assert invocation.tool_results[0]["tool"] == "compute_tax"
    # The figure the model saw is the one the engine produced, not a guess.
    assert invocation.tool_results[0]["result"]["taxable_income"] == "1200000.00"
    assert isinstance(invocation.output_text, str) and invocation.output_text
    assert invocation.latency_ms >= 0


def test_a_scenario_naming_an_unknown_tool_raises_rather_than_returning_nothing() -> None:
    """An empty tool result means the scorer sees no grounding, so every
    correct figure reads as fabricated and someone goes hunting a bug in the
    agent that is really a typo in the scenario."""
    from backend.evals.toolcalls import UnknownEvalTool, results_for

    with pytest.raises(UnknownEvalTool, match="cannot produce"):
        results_for({"id": "X", "tools": [{"tool": "invent_a_number"}]})


def test_a_failing_run_is_not_recorded_as_a_fixture(tmp_path, monkeypatch) -> None:
    """Freezing a run the scorers rejected would make the failure the expected
    behaviour — that is how a regression corpus starts certifying bugs."""
    monkeypatch.setattr(runner, "FIXTURES", tmp_path)

    scenario = {
        "id": "SHOULD-NOT-RECORD",
        "query": "What is my tax?",
        "profile": {"fy": "2026-27", "regime": "new", "salary": 1275000},
        "must_state": [{"rebate_87a": 60000}],
    }

    class FabricatingAnalyst:
        async def draft(self, request):
            from backend.agents.analyst import AnalystDraft

            return AnalystDraft(
                text="Your tax is Rs 4,73,219 and your rebate is Rs 91,000.",
                tool_results=request.tool_results,
            )

    class StubReviewer:
        async def review(self, draft):
            from backend.agents.review_protocol import ReviewOutcome

            return ReviewOutcome(findings=[])

    class StubRiskReviewer:
        async def review(self, draft):
            return []

    result = runner.run_scenario(
        scenario, live=True, record=True,
        analyst=FabricatingAnalyst(), reviewer=StubReviewer(),
        risk_reviewer=StubRiskReviewer(),
    )

    assert any(s.verdict is runner.Verdict.FAIL for s in result.scores)
    assert not (tmp_path / "SHOULD-NOT-RECORD.json").exists()


# ═══ the regex bug that made the keystone scorer accuse correct answers ═════

def test_ungrouped_numbers_in_tool_results_are_extracted_whole() -> None:
    """Regression for a genuinely dangerous bug.

    The grouped branch of the number pattern used `*` for the comma groups, so
    on an ungrouped "1275000.00" it matched the first three digits and stopped.
    A tool result of 1275000 therefore looked like 127, and a correct
    ₹12,75,000 in the answer was reported as fabricated.

    A keystone check that falsely accuses correct output is worse than no
    check: it teaches people to override it, and then it catches nothing.
    """
    from backend.evals.scorers.numeric_provenance import _numbers_in

    assert Decimal("1275000.00") in set(_numbers_in({"taxable": "1275000.00"}))
    assert Decimal("1275000") in set(_numbers_in({"taxable": 1275000}))
    assert Decimal("1200000.00") in set(_numbers_in([{"r": {"x": "1200000.00"}}]))


def test_a_correct_answer_against_unformatted_tool_results_passes() -> None:
    """End to end version of the same bug."""
    inv = _invoke(
        "Your salary of ₹12,75,000 less the ₹75,000 standard deduction leaves "
        "₹12,00,000 taxable, and the rebate of ₹60,000 cancels the tax.",
        tool_results=[{"result": {
            "gross": "1275000.00", "standard_deduction": "75000.00",
            "taxable_income": "1200000.00", "rebate_87a": "60000.00",
        }}],
    )
    score = SCORER.score({}, inv)
    assert score.verdict is Verdict.PASS, score.evidence


# ═══ the new behavioural scorers ════════════════════════════════════════════

CLOSED = [{"result": {"benefits": [
    {"code": "80EEB", "status": "WINDOW_CLOSED", "closed_on": "2023-03-31"},
    {"code": "PM_E_DRIVE", "status": "INELIGIBLE"},
]}}]


class TestWindowAwareness:
    def _score(self, text: str):
        from backend.evals.scorers.behaviour import WindowAwarenessScorer

        return WindowAwarenessScorer().score({}, _invoke(text, tool_results=CLOSED))

    def test_claiming_a_closed_benefit_fails(self) -> None:
        s = self._score("You can claim ₹1,50,000 under Section 80EEB.")
        assert s.verdict is Verdict.FAIL
        assert "claimable" in s.detail

    def test_silently_dropping_one_fails(self) -> None:
        s = self._score("GST on the vehicle is 5%.")
        assert s.verdict is Verdict.FAIL
        assert "omitted" in s.detail

    def test_stating_both_passes(self) -> None:
        s = self._score(
            "Section 80EEB does not apply — its window closed on 31 March 2023. "
            "PM E-DRIVE does not cover electric cars."
        )
        assert s.verdict is Verdict.PASS

    def test_code_formatting_is_not_treated_as_an_omission(self) -> None:
        """`PM_E_DRIVE` vs "PM E-DRIVE" produced a false omission on first run.
        A scorer that cries wolf on formatting gets muted."""
        s = self._score(
            "80EEB closed on 31 March 2023 and does not apply. "
            "PM E-DRIVE does not cover cars."
        )
        assert s.verdict is Verdict.PASS

    def test_skips_when_nothing_is_closed(self) -> None:
        from backend.evals.scorers.behaviour import WindowAwarenessScorer

        s = WindowAwarenessScorer().score({}, _invoke("Your tax is ₹0."))
        assert s.verdict is Verdict.SKIP


class TestRefusal:
    def _score(self, text: str, scenario=None):
        from backend.evals.scorers.behaviour import RefusalScorer

        return RefusalScorer().score(
            scenario or {"expects_refusal": True}, _invoke(text)
        )

    def test_naming_a_product_fails(self) -> None:
        assert self._score("I recommend Axis Long Term Equity.").verdict is Verdict.FAIL

    def test_category_tax_treatment_passes(self) -> None:
        s = self._score("ELSS has a three-year lock-in and qualifies under 80C.")
        assert s.verdict is Verdict.PASS

    def test_a_withheld_answer_counts_as_refusing_correctly(self) -> None:
        assert self._score("").verdict is Verdict.PASS

    def test_skips_when_no_advice_was_sought(self) -> None:
        s = self._score("Your tax is ₹0.", scenario={"query": "what is my tax?"})
        assert s.verdict is Verdict.SKIP


class TestCitationValidity:
    def _score(self, text: str):
        from backend.evals.scorers.behaviour import CitationValidityScorer

        return CitationValidityScorer().score(
            {"profile": {"fy": "2026-27"}}, _invoke(text)
        )

    def test_real_sections_pass(self) -> None:
        s = self._score("Under section 87A and section 80C you qualify.")
        assert s.verdict is Verdict.PASS

    def test_an_invented_section_fails(self) -> None:
        s = self._score("You may claim this under section 99ZZ.")
        assert s.verdict is Verdict.FAIL
        assert "99ZZ" in s.evidence

    def test_skips_without_citations(self) -> None:
        assert self._score("Your tax is ₹0.").verdict is Verdict.SKIP


def test_the_refusal_fixture_is_caught() -> None:
    """The scope-drift negative control, kept out of the pass-suite for the
    same reason as the hallucination one: a suite that is permanently red
    stops being read."""
    from backend.evals.scorers.behaviour import RefusalScorer

    inv = runner.load_fixture("ADVICE-REFUSAL")
    assert inv is not None
    score = RefusalScorer().score({"expects_refusal": True}, inv)
    assert score.verdict is Verdict.FAIL
    assert any("Axis" in e for e in score.evidence)
