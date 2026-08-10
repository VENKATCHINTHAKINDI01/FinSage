"""Assessment risk pass and scope guardrail — AGT-010, AGT-006.

Two failure modes are tested here, and the second matters as much as the first.

  Under-flagging: a thin claim ships unnoticed.
  Over-flagging:  every answer gets a warning, users learn warnings are noise,
                  and the thin claim ships unnoticed anyway — just with a
                  footnote nobody read.

`test_no_false_alarm_on_a_standard_documented_claim` is the counterweight. If
it ever fails, the risk pass has become decoration.
"""

from __future__ import annotations

import pytest

from backend.agents.analyst import Analyst
from backend.agents.pipeline import run
from backend.agents.review_protocol import Category, Verdict
from backend.agents.reviewer_ca import CAReviewer, DraftUnderReview
from backend.agents.reviewer_risk import (
    RiskReviewer,
    carries_a_claim,
    check_documentation_thin,
    check_scope,
)
from backend.llm import FakeLLM

FY = "2026-27"


def _d(text: str, **kw) -> DraftUnderReview:
    return DraftUnderReview(
        query=kw.pop("query", "How do I reduce my tax?"),
        draft=text,
        profile=kw.pop("profile", {}),
        tool_results=kw.pop("tool_results", []),
        fy=FY,
        regime=kw.pop("regime", "old"),
    )


# ═══ AGT-006 scope: the one thing this pass may block ═══════════════════════

@pytest.mark.parametrize(
    "text",
    [
        "You should invest in an ELSS fund to save tax.",
        "I recommend you buy a debt fund for this.",
        "The best fund for you is a large-cap index tracker.",
        "Consider HDFC Flexi Cap for the equity portion.",
    ],
)
def test_product_recommendations_are_blocked(text: str) -> None:
    """Personalised investment advice is SEBI-regulated. A tax product
    drifting into 'buy this' is a licensing problem, not a tone problem."""
    finding = check_scope(_d(text))
    assert finding is not None, f"scope drift not caught: {text!r}"
    assert finding.verdict is Verdict.BLOCK
    assert finding.category is Category.OUT_OF_SCOPE
    assert "SEBI" in finding.evidence["basis"]


@pytest.mark.parametrize(
    "text",
    [
        "ELSS carries a three-year lock-in and qualifies under Section 80C.",
        "Contributions to the NPS attract an additional ₹50,000 under 80CCD(1B).",
        "Debt fund units bought after April 2023 are taxed at your slab rate.",
        "Your tax under the new regime is ₹97,500.",
    ],
)
def test_tax_treatment_of_a_category_is_not_advice(text: str) -> None:
    """The guardrail must not swallow the product's actual job. Explaining how
    an instrument class is taxed is information, not a recommendation."""
    assert check_scope(_d(text)) is None, f"false positive on: {text!r}"


# ═══ AGT-010 conditionality ═════════════════════════════════════════════════

@pytest.mark.parametrize(
    "text,expected",
    [
        ("Your tax for FY 2026-27 is ₹97,500.", False),
        ("The new regime slabs start at ₹4,00,000.", False),
        ("You can claim ₹25,000 under Section 80D.", True),
        ("You are eligible for a deduction of ₹1,50,000.", True),
        ("This reduces your tax by ₹15,000.", True),
    ],
)
def test_only_answers_asserting_a_claim_get_the_risk_pass(text: str, expected: bool) -> None:
    """A computation needs no AO review. A position someone may have to defend
    does. This split is also what keeps the three-pass latency budget real."""
    assert carries_a_claim(text) is expected


async def test_informational_answers_skip_the_pass_entirely() -> None:
    findings = await RiskReviewer(llm=None).review(
        _d("Your tax for FY 2026-27 under the new regime is ₹97,500.")
    )
    assert findings == []


# ═══ documentation thinness ═════════════════════════════════════════════════

def test_a_claim_without_its_supporting_document_is_flagged() -> None:
    finding = check_documentation_thin(
        _d("You can claim ₹25,000 under Section 80D for your health cover.")
    )
    assert finding is not None
    assert finding.verdict is Verdict.FLAG, "documentation thinness is never a block"
    assert finding.category is Category.DOCUMENTATION_RISK
    assert "premium certificate" in finding.detail


def test_no_false_alarm_on_a_standard_documented_claim() -> None:
    """THE counterweight test.

    A reviewer that flags a well-documented, clearly-within-limits claim
    teaches users to ignore flags — and then a genuinely thin one slips past
    because it looks like all the others. If this test fails, the risk pass has
    become decoration.
    """
    finding = check_documentation_thin(
        _d(
            "You can claim ₹25,000 under Section 80D. Keep the insurer's "
            "premium certificate with your records."
        )
    )
    assert finding is None, "flagged a claim that already addressed its documentation"


def test_no_flag_where_no_claim_is_made() -> None:
    assert check_documentation_thin(_d("Section 80D allows up to ₹25,000.")) is None


def test_hra_claim_without_rent_receipts_is_flagged() -> None:
    finding = check_documentation_thin(
        _d("You can claim an exemption of ₹1,80,000 under 10(13A).")
    )
    assert finding is not None
    assert "landlord's PAN" in finding.detail


# ═══ the pass as a whole ════════════════════════════════════════════════════

async def test_scope_short_circuits_everything_else() -> None:
    findings = await RiskReviewer(llm=None).review(
        _d("You can claim ₹25,000 under 80D — and you should buy an ELSS fund.")
    )
    assert len(findings) == 1
    assert findings[0].category is Category.OUT_OF_SCOPE


async def test_risk_pass_emits_flags_not_blocks_for_documentation() -> None:
    findings = await RiskReviewer(llm=None).review(
        _d("You can claim ₹25,000 under Section 80D.")
    )
    assert findings and all(f.verdict is Verdict.FLAG for f in findings)


# ═══ through the full pipeline ══════════════════════════════════════════════

async def _pipeline(draft: str, **kw):
    return await run(
        query="How do I reduce my tax?",
        profile=kw.pop("profile", {}),
        fy=FY,
        tool_results=kw.pop("tool_results", []),
        regime=kw.pop("regime", "old"),
        analyst=Analyst(llm=FakeLLM(responses=[draft, draft])),
        reviewer=CAReviewer(llm=None),
        risk_reviewer=RiskReviewer(llm=None),
    )


async def test_scope_drift_withholds_the_answer_end_to_end() -> None:
    result = await _pipeline("You should invest in an ELSS fund to save tax.")
    assert result.answer.withheld
    assert "SEBI" in str(result.reviews[0].to_dict())


async def test_a_documentation_flag_still_serves_the_answer() -> None:
    """A thin claim is worth a note, not a refusal. The user still gets their
    answer; they also get told which line attracts questions."""
    result = await _pipeline("You can claim ₹25,000 under Section 80D.")
    assert not result.answer.withheld
    assert "₹25,000" in result.answer.text
    assert any("premium certificate" in n for n in result.answer.notes)


async def test_a_clean_informational_answer_gathers_no_notes() -> None:
    result = await _pipeline("Your tax under the old regime is ₹1,87,200.")
    assert not result.answer.withheld
    assert result.answer.notes == []
