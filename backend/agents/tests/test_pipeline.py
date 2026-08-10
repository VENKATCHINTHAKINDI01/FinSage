"""The full Analyst → Reviewer → answer path. AGT-008 + AGT-011.

Run with FakeLLM, so these are deterministic and need no key, no network and no
spend. The scripted responses are the point: each one is a specific way an
analyst can go wrong, and the test asserts what the pipeline does about it.
"""

from __future__ import annotations

from backend.agents.analyst import Analyst, AnalystRequest, render_tool_results
from backend.agents.pipeline import run, summarise_for_evidence_pack
from backend.agents.reviewer_ca import CAReviewer
from backend.llm import FakeLLM

FY = "2026-27"

CLOSED_80EEB = [
    {
        "tool": "evaluate_purchase_eligibility",
        "success": True,
        "result": {
            "benefits": [
                {"code": "80EEB", "status": "WINDOW_CLOSED",
                 "closed_on": "2023-03-31", "max_deduction": 150000}
            ]
        },
    },
    {
        "tool": "compute_landed_cost",
        "success": True,
        "result": {"base_price": 1800000, "gst_rate": 0.05,
                   "gst_amount": 90000, "landed_cost": 1890000},
    },
]

# The one profile where the old regime actually wins under FY 2026-27 — see
# test_review_pipeline.OLD_REGIME_WINS for how that was established.
OLD_WINS = {
    "salary": 1_500_000, "age": 35,
    "deductions": {"80C": 150_000, "80D": 25_000, "80CCD_1B": 50_000,
                   "24b": 200_000, "10_13A": 200_000},
}


async def _run(draft_texts: list[str], **kw):
    return await run(
        query=kw.pop("query", "What tax benefit do I get on an EV?"),
        profile=kw.pop("profile", {}),
        fy=FY,
        tool_results=kw.pop("tool_results", CLOSED_80EEB),
        regime=kw.pop("regime", "new"),
        analyst=Analyst(llm=FakeLLM(responses=draft_texts)),
        reviewer=CAReviewer(llm=None),
    )


# ═══ the v1 failure, end to end ═════════════════════════════════════════════

async def test_a_fabricated_claim_is_blocked_and_the_redraft_is_served() -> None:
    """The whole pipeline, doing its job.

    First draft claims a deduction whose window closed in 2023 — exactly what
    v1 produced. It is blocked, the analyst is told why, and the corrected
    second draft reaches the user.
    """
    result = await _run([
        "Good news — you can claim up to ₹1,50,000 under Section 80EEB on your "
        "EV loan interest.",
        "Section 80EEB is widely quoted for EVs, but you cannot claim it: the "
        "sanction window closed on 31 March 2023. On cost, GST on electric "
        "vehicles is 5%, so ₹90,000 on a base of ₹18,00,000.",
    ])

    assert not result.answer.withheld, "the corrected draft should have shipped"
    assert result.answer.redrafted
    assert len(result.drafts) == 2
    assert result.reviews[0].blocked and not result.reviews[1].blocked
    assert "closed on 31 March 2023" in result.answer.text


async def test_two_bad_drafts_withhold_rather_than_serve_the_second() -> None:
    """The important negative case. Falling back to the unreviewed draft would
    make the review a delay before a wrong answer."""
    bad = "You can claim ₹1,50,000 under Section 80EEB."
    result = await _run([bad, bad])

    assert result.answer.withheld
    assert bad not in result.answer.text
    assert "withheld" in result.answer.text.lower()
    assert "80EEB" in result.answer.failure_reason


async def test_a_clean_draft_passes_through_untouched() -> None:
    text = (
        "Section 80EEB would have given you ₹1,50,000, but the window closed on "
        "31 March 2023. GST on the vehicle is ₹90,000 at 5%."
    )
    result = await _run([text])

    assert result.answer.text == text
    assert not result.answer.redrafted
    assert len(result.drafts) == 1


# ═══ amendment ══════════════════════════════════════════════════════════════

async def test_an_omitted_cheaper_regime_is_appended_not_blocked() -> None:
    """Missing a better option is a real failure, but the answer is not wrong —
    so it is amended, not withheld."""
    result = await _run(
        ["Your tax for FY 2026-27 under the new regime is ₹97,500."],
        profile=OLD_WINS, regime="new", tool_results=[],
        query="How much tax do I owe?",
    )

    assert not result.answer.withheld
    assert "₹97,500" in result.answer.text, "the engine's figure must survive"
    assert "old regime" in result.answer.text.lower()
    assert "16,900" in result.answer.text


async def test_the_analyst_cannot_paraphrase_an_amendment_away() -> None:
    """Amendments are appended verbatim by the protocol, not fed back to the
    model to reword. A caveat the analyst finds inconvenient is not negotiable."""
    result = await _run(
        ["Your tax under the new regime is ₹97,500."],
        profile=OLD_WINS, regime="new", tool_results=[],
    )
    amendment = result.reviews[0].amendments[0].amendment
    assert amendment in result.answer.text


# ═══ failure handling ═══════════════════════════════════════════════════════

async def test_a_model_failure_says_so_rather_than_improvising() -> None:
    result = await run(
        query="How much tax?", profile={}, fy=FY, tool_results=[],
        analyst=Analyst(llm=FakeLLM(responses=[])),   # raises on first call
        reviewer=CAReviewer(llm=None),
    )
    assert result.answer.withheld
    assert "could not produce an answer" in result.answer.text
    assert "Nothing was computed incorrectly" in result.answer.text


async def test_no_model_configured_is_not_a_silent_empty_answer() -> None:
    result = await run(
        query="q", profile={}, fy=FY, tool_results=[],
        analyst=Analyst(llm=None), reviewer=CAReviewer(llm=None),
    )
    assert result.answer.withheld
    assert result.answer.failure_reason == "no model configured"


# ═══ cost and telemetry ═════════════════════════════════════════════════════

async def test_a_clean_answer_costs_exactly_one_model_call() -> None:
    """The reviewer's deterministic checks are free. Only the framing pass
    costs a call, and it is skipped when no model is attached."""
    result = await _run([
        "Section 80EEB closed on 31 March 2023. GST is ₹90,000."
    ])
    assert result.llm_calls == 1


async def test_a_redraft_costs_two() -> None:
    result = await _run([
        "You can claim ₹1,50,000 under Section 80EEB.",
        "Section 80EEB closed on 31 March 2023, so it does not apply.",
    ])
    assert result.llm_calls == 2


# ═══ the analyst's own contract ═════════════════════════════════════════════

async def test_the_analyst_is_told_the_tool_results_are_the_only_figures() -> None:
    llm = FakeLLM(responses=["ok"])
    await Analyst(llm=llm).draft(
        AnalystRequest(query="q", profile={}, fy=FY, tool_results=CLOSED_80EEB)
    )
    assert "THESE ARE THE ONLY FIGURES YOU MAY USE" in llm.calls[0]


async def test_a_redraft_carries_the_rejection_reason() -> None:
    llm = FakeLLM(responses=["ok"])
    await Analyst(llm=llm).draft(
        AnalystRequest(
            query="q", profile={}, fy=FY, tool_results=[],
            revision_note="claimed 80EEB, whose window closed",
        )
    )
    prompt = llm.calls[0]
    assert "REJECTED IN REVIEW" in prompt
    assert "window closed" in prompt
    assert "softer language" in prompt, "must not just re-hedge the same claim"


def test_no_tool_results_means_no_figures_permitted() -> None:
    assert "cannot state any figure" in render_tool_results([])


def test_a_failed_tool_is_shown_as_failed_not_omitted() -> None:
    rendered = render_tool_results(
        [{"tool": "compute_tax", "success": False, "error": "engine down"}]
    )
    assert "FAILED" in rendered and "engine down" in rendered


# ═══ evidence pack ══════════════════════════════════════════════════════════

async def test_the_pack_records_findings_that_were_resolved() -> None:
    """A pack showing only the final answer would hide that a reviewer objected
    and the objection was fixed — the part a checker most wants to see."""
    result = await _run([
        "You can claim ₹1,50,000 under Section 80EEB.",
        "Section 80EEB closed on 31 March 2023, so it does not apply to you.",
    ])
    pack = summarise_for_evidence_pack(result)

    assert pack["reviewed"] and pack["redrafted"]
    assert not pack["withheld"]
    assert pack["verdict_counts"]["block"] == 1
    assert pack["findings_by_category"]["fabricated_figure"] == 1


async def test_pipeline_result_serialises() -> None:
    result = await _run(["Section 80EEB closed on 31 March 2023."])
    d = result.to_dict()
    assert d["draft_count"] == 1
    assert d["llm_calls"] == 1
    assert d["total_latency_ms"] >= 0
