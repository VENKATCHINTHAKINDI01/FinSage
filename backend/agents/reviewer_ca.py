"""Reviewer — chartered accountant file-review pass. AGT-009.

Why this is not two LLMs marking each other's homework
-------------------------------------------------------
If the Analyst computed a number with a model and this agent re-checked it with
a model, the two would fail together. They share training data and failure
modes, so agreement between them is weak evidence, and "two experts concurred"
manufactures confidence nobody earned.

This reviewer therefore does not re-derive arithmetic. `backend/core` already
did that, deterministically, with 347 tests behind it. What a second reader is
genuinely good at — and what a test suite cannot do — is noticing what is *not*
there:

    the old regime is cheaper and the answer never mentioned it
    a benefit's window closed and the answer just omitted it
    the numbers are right but the framing implies a certainty they lack
    a field was never asked for that would change the answer

Every one of those checks is grounded by calling the engine directly. When this
agent says "you should have mentioned the old regime is ₹40,120 cheaper", that
₹40,120 came from `compute_tax`, not from a model's impression. The challenge is
deterministically proven; only the *decision to look* is model-driven.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from backend.agents.review_protocol import (
    Category,
    Finding,
    ReviewOutcome,
    Verdict,
)
from backend.tools.calculation import TaxCalculationEngine

logger = logging.getLogger(__name__)


def _fmt(amount: Decimal) -> str:
    """Indian digit grouping for prose. The engine owns the value; this only
    formats it."""
    whole = int(amount)
    s = str(abs(whole))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join([*parts, tail])
    return f"₹{s}"


@dataclass(slots=True)
class DraftUnderReview:
    """What the reviewer is given."""

    query: str
    draft: str
    profile: dict[str, Any]
    tool_results: list[dict[str, Any]]
    fy: str
    regime: str = "new"


# ═══════════════════════════════════════════════════════════════════════════
# Deterministic checks — no model involved at all
# ═══════════════════════════════════════════════════════════════════════════
#
# These run first and are the reviewer's spine. A model is only needed for
# judgement calls about tone and framing; everything below is decidable.


def check_omitted_better_regime(d: DraftUnderReview) -> Finding | None:
    """The single most valuable thing a reviewer catches.

    A taxpayer defaulted into the new regime who would pay materially less
    under the old one is losing real money, and an answer that computes the new
    regime correctly while never mentioning the alternative is accurate and
    useless.
    """
    income = d.profile.get("salary") or d.profile.get("income") or 0
    if not income or float(income) <= 0:
        return None

    # Reached through the tools adapter rather than importing the engine
    # directly. The import-linter contract "agents reach the core only through
    # tools" caught the direct import, and the contract is right: the adapter
    # IS the sanctioned path, and routing through it costs the reviewer nothing.
    # It still verifies independently — that is what makes its challenges
    # deterministic rather than opinions.
    comparison = TaxCalculationEngine.compare_regimes(
        gross_income=income,
        deductions=d.profile.get("deductions") or {},
        fy=d.fy,
        age=int(d.profile.get("age", 0)),
    )

    better = comparison["better_regime"]
    saving_raw = Decimal(comparison["saving"])

    if better == d.regime or saving_raw <= 0:
        return None
    saving = _fmt(saving_raw)

    # Mentioned already? Then it is not an omission.
    mentioned = f"{better} regime" in d.draft.lower() or f"{better} tax regime" in d.draft.lower()
    if mentioned:
        return None

    return Finding(
        verdict=Verdict.AMEND,
        category=Category.OMITTED_OPTION,
        detail=(
            f"The {better} regime is {saving} cheaper for this profile and the "
            f"answer does not mention it."
        ),
        evidence={
            "check": "compute_tax both regimes",
            "fy": d.fy,
            "old_total_tax": comparison["old"]["total_tax"],
            "new_total_tax": comparison["new"]["total_tax"],
            "better": better,
            "saving": comparison["saving"],
        },
        amendment=(
            f"Worth knowing: on these figures the {better} regime works out "
            f"{saving} cheaper for you. This calculation assumes the deductions "
            f"listed above; confirm them before switching, and note the choice "
            f"is not freely reversible every year if you have business income."
        ),
    )


def check_dropped_closed_window(d: DraftUnderReview) -> Finding | None:
    """A closed benefit that was silently omitted rather than stated.

    Silence reads as "there was nothing here". Saying "80EEB would have given
    you ₹1.5L but the window closed on 31 March 2023" is more useful, and it is
    the kind of thing that makes a user believe the rest of the output.
    """
    closed = []
    for result in d.tool_results:
        payload = result.get("result", {}) if isinstance(result, dict) else {}
        for benefit in payload.get("benefits", []) or []:
            if benefit.get("status") == "WINDOW_CLOSED":
                closed.append(benefit)

    unmentioned = [
        b for b in closed if str(b.get("code", "")).lower() not in d.draft.lower()
    ]
    if not unmentioned:
        return None

    first = unmentioned[0]
    code = first.get("code", "a benefit")
    when = first.get("closed_on", "an earlier date")

    return Finding(
        verdict=Verdict.AMEND,
        category=Category.DROPPED_WINDOW,
        detail=f"{code} came back WINDOW_CLOSED and the answer omits it entirely.",
        evidence={
            "check": "eligibility outcome present in tool results",
            "code": code,
            "status": "WINDOW_CLOSED",
            "closed_on": when,
        },
        amendment=(
            f"One thing you may have read about elsewhere: {code} is often "
            f"listed as available, but its window closed on {when}, so it does "
            f"not apply to you. We mention it so you are not left wondering."
        ),
    )


def check_claims_a_closed_benefit(d: DraftUnderReview) -> Finding | None:
    """The inverse, and far more serious: the draft claims something closed.

    This is a BLOCK. An answer telling a user they can claim a deduction they
    cannot is the failure this entire rebuild exists to prevent.
    """
    for result in d.tool_results:
        payload = result.get("result", {}) if isinstance(result, dict) else {}
        for benefit in payload.get("benefits", []) or []:
            code = str(benefit.get("code", ""))
            if benefit.get("status") not in ("WINDOW_CLOSED", "INELIGIBLE"):
                continue
            if not code or code.lower() not in d.draft.lower():
                continue

            lowered = d.draft.lower()
            asserts_entitlement = any(
                phrase in lowered
                for phrase in ("you can claim", "you may claim", "you are eligible",
                               "you qualify", "claim up to", "you will get")
            )
            acknowledges = any(
                phrase in lowered
                for phrase in ("closed", "does not apply", "not available",
                               "no longer", "cannot claim", "would have")
            )
            if asserts_entitlement and not acknowledges:
                return Finding(
                    verdict=Verdict.BLOCK,
                    category=Category.FABRICATED_FIGURE,
                    detail=(
                        f"The answer presents {code} as claimable, but the "
                        f"eligibility engine returned "
                        f"{benefit.get('status')}."
                    ),
                    evidence={
                        "check": "eligibility outcome vs draft assertion",
                        "code": code,
                        "engine_status": benefit.get("status"),
                        "closed_on": benefit.get("closed_on"),
                    },
                )
    return None


def check_unasked_material_question(d: DraftUnderReview) -> Finding | None:
    """A field we never asked for that would change the answer.

    Only fires where the missing field is genuinely material, so it does not
    become a nag on every response.
    """
    if d.regime != "old":
        return None
    income = d.profile.get("salary") or 0
    if not income or float(income) <= 0:
        return None
    if d.profile.get("rent_paid") is not None:
        return None
    if "hra" in d.draft.lower() or "rent" in d.draft.lower():
        return None

    return Finding(
        verdict=Verdict.FLAG,
        category=Category.UNASKED_QUESTION,
        detail=(
            "Rent paid was never captured. Under the old regime an HRA "
            "exemption can be material and this answer silently assumes none."
        ),
        evidence={"check": "profile completeness", "missing_field": "rent_paid"},
    )


DETERMINISTIC_CHECKS = (
    check_claims_a_closed_benefit,   # BLOCK first — most serious
    check_omitted_better_regime,
    check_dropped_closed_window,
    check_unasked_material_question,
)


# ═══════════════════════════════════════════════════════════════════════════
# The reviewer
# ═══════════════════════════════════════════════════════════════════════════

REVIEW_SYSTEM_PROMPT = """You are reviewing a colleague's draft advice to a \
client, to the standard a chartered accountant applies to a file before it \
leaves the office.

You are NOT checking arithmetic. Every figure was computed by a deterministic \
engine and is correct. Re-deriving it would waste your time and risk \
introducing an error the engine did not make.

You are checking for the things a calculation cannot catch:
  - claims stated with more certainty than the facts support
  - a conditional saving presented as if already achieved
  - advice that strays into recommending specific investment products
  - tone that would embarrass the firm if the client forwarded it

Respond in JSON:
{"findings": [{"verdict": "flag", "category": "misleading_framing",
               "detail": "..."}]}

Use "flag" only. Blocking and amending require engine evidence, which you do \
not have — those findings come from the deterministic checks. If the draft \
reads fairly, return {"findings": []}. Do not invent problems; a reviewer who \
always finds something gets ignored."""


class CAReviewer:
    """Runs deterministic checks, then optionally a model pass on framing."""

    name = "reviewer_ca"

    def __init__(self, llm: Any | None = None) -> None:
        self._llm = llm

    async def review(self, d: DraftUnderReview) -> ReviewOutcome:
        findings: list[Finding] = []

        for check in DETERMINISTIC_CHECKS:
            try:
                finding = check(d)
            except Exception:
                # A broken check must not take down the answer, but it must not
                # pass silently either.
                logger.exception("reviewer check %s failed", check.__name__)
                continue
            if finding:
                findings.append(finding)
                if finding.verdict is Verdict.BLOCK:
                    # Nothing after a block matters; the answer is not shipping.
                    break

        if not any(f.verdict is Verdict.BLOCK for f in findings):
            findings.extend(await self._framing_pass(d))

        findings.sort(key=lambda f: f.verdict.rank)
        return ReviewOutcome(findings=findings)

    async def _framing_pass(self, d: DraftUnderReview) -> list[Finding]:
        """Model judgement on tone and overstatement. FLAG only."""
        if self._llm is None:
            return []
        try:
            resp = await self._llm.complete(
                f"Client question:\n{d.query}\n\nDraft advice:\n{d.draft}",
                system=REVIEW_SYSTEM_PROMPT,
                json_mode=True,
                max_tokens=600,
            )
            raw = resp.json()
        except Exception:
            logger.warning("framing pass unavailable; deterministic checks stand")
            return []

        out: list[Finding] = []
        for item in (raw.get("findings") or [])[:5]:
            try:
                category = Category(item.get("category", "misleading_framing"))
            except ValueError:
                category = Category.MISLEADING_FRAMING
            detail = str(item.get("detail", "")).strip()
            if detail:
                # Forced to FLAG regardless of what the model asked for. A model
                # cannot block or amend, because it has no evidence to offer.
                out.append(
                    Finding(Verdict.FLAG, category, detail, reviewer=self.name)
                )
        return out
