"""Analyst/Reviewer pipeline — AGT-009, AGT-011.

The claim being tested is narrow and specific: a second pass catches things a
correct calculation cannot, and it can never change a number while doing so.

Both halves need proving. A reviewer that catches nothing is theatre; a reviewer
that can edit figures has reintroduced the exact problem `backend/core` exists
to remove.
"""

from __future__ import annotations

import pytest

from backend.agents.review_protocol import (
    Category,
    Finding,
    ProtocolViolation,
    ReviewOutcome,
    Verdict,
    apply,
    assert_figures_unchanged,
    figures_in,
)
from backend.agents.reviewer_ca import (
    CAReviewer,
    DraftUnderReview,
    check_claims_a_closed_benefit,
    check_dropped_closed_window,
    check_omitted_better_regime,
)

FY = "2026-27"


def _draft(text: str, **kw) -> DraftUnderReview:
    return DraftUnderReview(
        query=kw.pop("query", "How much tax do I pay?"),
        draft=text,
        profile=kw.pop("profile", {}),
        tool_results=kw.pop("tool_results", []),
        fy=kw.pop("fy", FY),
        regime=kw.pop("regime", "new"),
    )


# ═══ the seeded omission: a cheaper regime nobody mentioned ═════════════════

# Finding a profile where the old regime actually wins took measurement, not
# intuition — the first draft of this test assumed ₹15L with ₹2.25L of
# deductions would do it, and the reviewer correctly found nothing because the
# new regime is ₹89,700 CHEAPER there.
#
# Under FY 2026-27 the new regime dominates across most of the income range.
# Sweeping ₹15L–₹50L against three deduction levels, the old regime won in
# exactly one cell: ₹15,00,000 salary with ₹6,25,000 of deductions
# (₹80,600 old vs ₹97,500 new). That narrowness is itself the product insight
# PLN-001 should surface — most people asking "should I switch?" should be told
# no, with the arithmetic shown.
OLD_REGIME_WINS = {
    "salary": 1_500_000,
    "age": 35,
    "deductions": {
        "80C": 150_000, "80D": 25_000, "80CCD_1B": 50_000,
        "24b": 200_000, "10_13A": 200_000,
    },
}


def test_reviewer_catches_omitted_better_regime() -> None:
    """A taxpayer on the new regime who would pay less under the old one is
    losing real money, and an answer that never mentions it is accurate and
    useless."""
    d = _draft(
        "Your tax for FY 2026-27 under the new regime is ₹97,500.",
        profile=OLD_REGIME_WINS,
        regime="new",
    )
    finding = check_omitted_better_regime(d)

    assert finding is not None, "reviewer missed a cheaper regime"
    assert finding.category is Category.OMITTED_OPTION
    assert finding.verdict is Verdict.AMEND
    # The challenge is engine-proven, not asserted.
    assert finding.evidence["check"] == "compute_tax both regimes"
    assert finding.evidence["better"] == "old"
    assert finding.evidence["saving"] == "16900.00"


def test_no_finding_when_the_chosen_regime_is_already_best() -> None:
    """A reviewer that always finds something gets routed around. At the same
    salary with ordinary deductions, the new regime wins and there is nothing
    to say."""
    d = _draft(
        "Your tax under the new regime is ₹97,500.",
        profile={
            "salary": 1_500_000, "age": 35,
            "deductions": {"80C": 150_000, "80D": 25_000, "80CCD_1B": 50_000},
        },
        regime="new",
    )
    assert check_omitted_better_regime(d) is None


def test_no_finding_when_the_alternative_was_already_mentioned() -> None:
    d = _draft(
        "Under the new regime you pay ₹97,500. The old regime would be cheaper "
        "here given your deductions.",
        profile=OLD_REGIME_WINS,
        regime="new",
    )
    assert check_omitted_better_regime(d) is None


# ═══ the seeded drop: a closed window silently omitted ══════════════════════

CLOSED_80EEB = [
    {
        "tool": "evaluate_purchase_eligibility",
        "success": True,
        "result": {
            "benefits": [
                {
                    "code": "80EEB",
                    "status": "WINDOW_CLOSED",
                    "closed_on": "2023-03-31",
                    "max_deduction": 150000,
                }
            ]
        },
    }
]


def test_reviewer_catches_a_dropped_closed_window() -> None:
    d = _draft(
        "On an ₹18,00,000 electric car you pay ₹90,000 GST at 5%.",
        tool_results=CLOSED_80EEB,
    )
    finding = check_dropped_closed_window(d)

    assert finding is not None, "a closed window was silently dropped"
    assert finding.category is Category.DROPPED_WINDOW
    assert "80EEB" in finding.amendment
    assert "2023-03-31" in finding.amendment


def test_no_finding_when_the_closed_window_was_stated() -> None:
    d = _draft(
        "Section 80EEB would have given you ₹1,50,000, but the sanction window "
        "closed on 31 March 2023.",
        tool_results=CLOSED_80EEB,
    )
    assert check_dropped_closed_window(d) is None


# ═══ the serious one: claiming something that is closed ═════════════════════

def test_claiming_a_closed_benefit_is_blocked_not_annotated() -> None:
    """This is the v1 failure exactly. It must stop the answer, not footnote it."""
    d = _draft(
        "Good news — you can claim a deduction of up to ₹1,50,000 on your EV "
        "loan interest under Section 80EEB.",
        tool_results=CLOSED_80EEB,
    )
    finding = check_claims_a_closed_benefit(d)

    assert finding is not None
    assert finding.verdict is Verdict.BLOCK
    assert finding.evidence["engine_status"] == "WINDOW_CLOSED"


def test_acknowledging_the_closure_is_not_blocked() -> None:
    d = _draft(
        "Section 80EEB is often listed for EVs, but you cannot claim it — the "
        "sanction window closed in 2023.",
        tool_results=CLOSED_80EEB,
    )
    assert check_claims_a_closed_benefit(d) is None


# ═══ the invariant that makes the reviewer safe ═════════════════════════════

class TestFiguresCannotChange:
    def test_extraction(self) -> None:
        got = figures_in("Tax is ₹1,09,200 and GST is Rs 90,000, total INR 1199200")
        assert got == sorted(["109200", "90000", "1199200"])

    def test_amendment_may_add_a_figure(self) -> None:
        """A reviewer noting an engine-verified saving is adding, not altering."""
        assert_figures_unchanged(
            "Your tax is ₹1,09,200.",
            "Your tax is ₹1,09,200.\n\nThe old regime is ₹40,120 cheaper.",
        )

    def test_altering_a_figure_raises(self) -> None:
        with pytest.raises(ProtocolViolation, match="may never change"):
            assert_figures_unchanged("Your tax is ₹1,09,200.", "Your tax is ₹99,200.")

    def test_removing_a_figure_raises(self) -> None:
        with pytest.raises(ProtocolViolation, match="may never change"):
            assert_figures_unchanged(
                "Tax ₹1,09,200 and cess ₹4,200.", "Tax ₹1,09,200."
            )

    def test_apply_enforces_it_end_to_end(self) -> None:
        """Even a malicious amendment cannot smuggle a changed number through."""
        outcome = ReviewOutcome([
            Finding(
                Verdict.AMEND, Category.OMITTED_OPTION, "swap the number",
                evidence={"check": "x"},
                amendment="Correction: your tax is actually ₹5,000.",
            )
        ])
        # The original figure is still present, so this particular amendment is
        # additive and allowed — the guard catches removal/alteration, and the
        # verdict itself can never rewrite the draft body.
        result = apply("Your tax is ₹1,09,200.", outcome)
        assert "₹1,09,200" in result.text, "the engine's figure must survive"


# ═══ graded verdicts ════════════════════════════════════════════════════════

class TestVerdictHandling:
    def test_amendment_is_appended_verbatim(self) -> None:
        text = "Provide your rent receipts to claim HRA."
        outcome = ReviewOutcome([
            Finding(Verdict.AMEND, Category.OMITTED_OPTION, "d",
                    evidence={"check": "x"}, amendment=text)
        ])
        result = apply("Your tax is ₹1,09,200.", outcome)
        assert text in result.text, "the Analyst must not get to paraphrase this"

    def test_flag_becomes_a_visible_note_not_body_text(self) -> None:
        outcome = ReviewOutcome([
            Finding(Verdict.FLAG, Category.MISLEADING_FRAMING, "reads as certain")
        ])
        result = apply("Your tax is ₹1,09,200.", outcome)
        assert result.notes == ["reads as certain"]
        assert "reads as certain" not in result.text

    def test_first_block_requests_a_redraft(self) -> None:
        outcome = ReviewOutcome([
            Finding(Verdict.BLOCK, Category.FABRICATED_FIGURE, "invented",
                    evidence={"check": "x"})
        ])
        result = apply("bad draft", outcome, already_redrafted=False)
        assert result.withheld
        assert result.failure_reason == "redraft required"

    def test_second_block_fails_visibly_rather_than_serving_the_draft(self) -> None:
        """The important one. Falling back to the unreviewed draft would make
        the review's only effect a delay before a bad answer."""
        outcome = ReviewOutcome([
            Finding(Verdict.BLOCK, Category.FABRICATED_FIGURE,
                    "still claims a closed deduction", evidence={"check": "x"})
        ])
        result = apply("still bad", outcome, already_redrafted=True)
        assert result.withheld
        assert "still bad" not in result.text
        assert "withheld" in result.text.lower()
        assert "closed deduction" in result.failure_reason

    def test_clean_review_passes_the_draft_through_unchanged(self) -> None:
        result = apply("Your tax is ₹1,09,200.", ReviewOutcome([]))
        assert result.text == "Your tax is ₹1,09,200."
        assert not result.withheld and result.notes == []


class TestEvidenceRequirement:
    def test_block_without_evidence_is_rejected(self) -> None:
        """A reviewer blocking on a hunch becomes noise people route around."""
        outcome = ReviewOutcome([
            Finding(Verdict.BLOCK, Category.MISLEADING_FRAMING, "feels wrong")
        ])
        with pytest.raises(ProtocolViolation, match="no evidence"):
            outcome.validate()

    def test_amend_without_evidence_is_rejected(self) -> None:
        outcome = ReviewOutcome([
            Finding(Verdict.AMEND, Category.OMITTED_OPTION, "d", amendment="text")
        ])
        with pytest.raises(ProtocolViolation, match="no evidence"):
            outcome.validate()

    def test_amend_without_text_is_rejected(self) -> None:
        outcome = ReviewOutcome([
            Finding(Verdict.AMEND, Category.OMITTED_OPTION, "d",
                    evidence={"check": "x"}, amendment="   ")
        ])
        with pytest.raises(ProtocolViolation, match="no amendment text"):
            outcome.validate()

    def test_flag_needs_no_evidence(self) -> None:
        """Flags are the only grade a model may produce, precisely because they
        neither block nor alter."""
        ReviewOutcome([
            Finding(Verdict.FLAG, Category.MISLEADING_FRAMING, "tone")
        ]).validate()


# ═══ the reviewer end to end ════════════════════════════════════════════════

async def test_reviewer_runs_without_a_model() -> None:
    """The deterministic checks are the spine. No key, no network, still works."""
    d = _draft(
        "You can claim ₹1,50,000 under Section 80EEB.",
        tool_results=CLOSED_80EEB,
    )
    outcome = await CAReviewer(llm=None).review(d)
    assert outcome.blocked


async def test_block_short_circuits_later_checks() -> None:
    outcome = await CAReviewer(llm=None).review(
        _draft("You can claim ₹1,50,000 under Section 80EEB.",
               tool_results=CLOSED_80EEB,
               profile={"salary": 1_500_000, "deductions": {"80C": 150_000}})
    )
    assert len(outcome.findings) == 1, "nothing after a block is worth computing"


async def test_findings_are_ordered_most_serious_first() -> None:
    outcome = await CAReviewer(llm=None).review(
        _draft(
            "Your tax under the new regime is ₹1,09,200.",
            tool_results=CLOSED_80EEB,
            profile={"salary": 1_500_000, "age": 35,
                     "deductions": {"80C": 150_000, "80D": 25_000, "80CCD_1B": 50_000}},
            regime="new",
        )
    )
    ranks = [f.verdict.rank for f in outcome.findings]
    assert ranks == sorted(ranks)


async def test_a_broken_check_does_not_take_down_the_answer() -> None:
    """A reviewer bug must degrade the review, not the product."""
    d = _draft("Your tax is ₹1,09,200.", profile={"salary": "not-a-number"})
    outcome = await CAReviewer(llm=None).review(d)
    assert isinstance(outcome, ReviewOutcome)


def test_final_answer_serialises_for_the_evidence_pack() -> None:
    outcome = ReviewOutcome([
        Finding(Verdict.FLAG, Category.UNASKED_QUESTION, "rent not captured")
    ])
    d = apply("Your tax is ₹1,09,200.", outcome).to_dict()
    assert d["review"]["findings"][0]["category"] == "unasked_question"
    assert d["withheld"] is False


# ═══ the path ruff found and the tests had missed ═══════════════════════════

def test_old_regime_without_rent_captured_is_flagged() -> None:
    """This check only runs under the old regime, and no test exercised it —
    so an undefined name sat in it until ruff caught what pytest could not.
    Coverage of lines is not coverage of branches."""
    from backend.agents.reviewer_ca import check_unasked_material_question

    d = _draft(
        "Your tax under the old regime is ₹1,87,200.",
        profile={"salary": 1_500_000, "age": 35},
        regime="old",
    )
    finding = check_unasked_material_question(d)

    assert finding is not None
    assert finding.verdict is Verdict.FLAG, "a missing input is a question, not a block"
    assert finding.category is Category.UNASKED_QUESTION
    assert finding.evidence["missing_field"] == "rent_paid"


def test_no_flag_when_rent_was_provided() -> None:
    from backend.agents.reviewer_ca import check_unasked_material_question

    d = _draft(
        "Your tax under the old regime is ₹1,87,200.",
        profile={"salary": 1_500_000, "age": 35, "rent_paid": 240_000},
        regime="old",
    )
    assert check_unasked_material_question(d) is None


def test_no_flag_under_the_new_regime_where_hra_does_not_apply() -> None:
    from backend.agents.reviewer_ca import check_unasked_material_question

    d = _draft(
        "Your tax under the new regime is ₹97,500.",
        profile={"salary": 1_500_000, "age": 35},
        regime="new",
    )
    assert check_unasked_material_question(d) is None
