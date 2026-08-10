"""Reviewer — assessment risk pass. AGT-010 + AGT-006.

The CA pass asks "is this right and complete?". This one asks a different
question: "if the department looked at this, what would they ask about?"

The failure mode of an AO-voiced reviewer is over-caution. Left unchecked it
flags every legitimate claim as risky, the user learns that everything is
flagged, and the flags stop meaning anything — at which point a genuinely thin
claim passes unnoticed because it looks like all the others. So:

  * it runs ONLY when the output contains an actual claim or recommendation.
    A purely informational answer skips it entirely, which is also what keeps
    the three-pass latency budget reachable.
  * `risk_pass_no_false_alarm` is a first-class eval: flagging a fully
    documented standard claim is a FAILURE, not caution.
  * it emits FLAG only. It cannot block, and it cannot amend.

The scope guardrail (AGT-006) lives here too, because it is the same kind of
question — what would embarrass us — and it is the one thing in this module
that CAN block. Personalised investment advice is SEBI-regulated, and a tax
product drifting into "buy this fund" is not a caution issue, it is a licensing
one.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from backend.agents.review_protocol import Category, Finding, Verdict
from backend.agents.reviewer_ca import DraftUnderReview

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# AGT-006 — scope. The one thing this pass may block.
# ═══════════════════════════════════════════════════════════════════════════

# Naming a product category and its tax treatment is fine and useful.
# Recommending a specific instrument to a specific person is regulated advice.
_RECOMMENDS = re.compile(
    r"\b(?:you should (?:buy|invest in|purchase|switch to)"
    r"|i (?:recommend|suggest) (?:you )?(?:buy|invest|put)"
    r"|the best (?:fund|stock|scheme|investment) (?:is|would be|for you)"
    r"|go (?:with|for) (?:the )?[A-Z])",
    re.IGNORECASE,
)

# A named product, as opposed to a category. "ELSS" is a category; "Axis ELSS
# Fund" is a product.
_NAMED_PRODUCT = re.compile(
    r"\b(?:HDFC|ICICI|SBI|Axis|Kotak|Nippon|Mirae|Parag Parikh|Quant|UTI|"
    r"Aditya Birla|Franklin|DSP|Tata|Motilal|Edelweiss)\s+\w+",
)


def check_scope(d: DraftUnderReview) -> Finding | None:
    """Personalised investment advice is outside what this product may say.

    Explaining that ELSS carries a three-year lock-in and qualifies under 80C
    is tax information. Telling someone which ELSS fund to buy is advice a
    SEBI-registered adviser gives, and we are not one.
    """
    named = _NAMED_PRODUCT.search(d.draft)
    recommends = _RECOMMENDS.search(d.draft)

    if not (named or recommends):
        return None

    detail = (
        "The answer recommends a specific investment"
        + (f" ('{named.group(0)}')" if named else "")
        + ". Personalised investment advice is SEBI-regulated and outside "
        "this product's remit."
    )
    return Finding(
        verdict=Verdict.BLOCK,
        category=Category.OUT_OF_SCOPE,
        detail=detail,
        evidence={
            "check": "scope pattern match",
            "matched": (named or recommends).group(0),
            "basis": "SEBI (Investment Advisers) Regulations, 2013",
        },
        reviewer="risk",
    )


# ═══════════════════════════════════════════════════════════════════════════
# Does this answer even need a risk pass?
# ═══════════════════════════════════════════════════════════════════════════

_CLAIM_LANGUAGE = re.compile(
    r"\b(?:you can claim|you may claim|eligible for|deduction of|"
    r"exemption of|you will save|reduces your tax|claim up to)\b",
    re.IGNORECASE,
)


def carries_a_claim(draft: str) -> bool:
    """Only answers asserting an entitlement get the risk pass.

    "Your tax is ₹97,500" is a computation and needs no AO review. "You can
    claim ₹1,50,000 under 80C" is a position someone may have to defend.
    """
    return bool(_CLAIM_LANGUAGE.search(draft))


# ═══════════════════════════════════════════════════════════════════════════
# Documentation thinness — deterministic, and deliberately narrow
# ═══════════════════════════════════════════════════════════════════════════

# Claims that routinely attract a query, and the document that answers it.
# Kept short on purpose. A long list becomes a nag, and a nag becomes noise.
_SUPPORTING_DOCUMENT = {
    "80D": "the insurer's premium certificate",
    "80DDB": "the prescribed specialist's certificate in Form 10-I",
    "80G": "the donation receipt with the institution's 80G registration number",
    "10(13A)": "rent receipts, and the landlord's PAN where annual rent exceeds ₹1,00,000",
    "80GG": "Form 10BA",
    "80U": "the disability certificate",
    "80DD": "the disability certificate for the dependant",
}


def check_documentation_thin(d: DraftUnderReview) -> Finding | None:
    """Flag a claimed deduction whose supporting document was never mentioned.

    This is not a suggestion that the claim is wrong. It is the thing a CA
    would say handing the file back: keep the paperwork, because this is the
    line that gets queried.
    """
    if not carries_a_claim(d.draft):
        return None

    lowered = d.draft.lower()
    for code, document in _SUPPORTING_DOCUMENT.items():
        if code.lower() not in lowered:
            continue
        # Already addressed? Then nothing to add.
        first_word = document.split()[0].lower().rstrip(",")
        if first_word in lowered or "receipt" in lowered or "certificate" in lowered:
            continue
        return Finding(
            verdict=Verdict.FLAG,
            category=Category.DOCUMENTATION_RISK,
            detail=(
                f"{code} is claimed without mentioning {document}. This is the "
                f"line most often queried on assessment."
            ),
            evidence={"check": "claimed deduction vs documentation mentioned",
                      "code": code, "expected_document": document},
            reviewer="risk",
        )
    return None


# ═══════════════════════════════════════════════════════════════════════════

RISK_SYSTEM_PROMPT = """You are an Assessing Officer reading a taxpayer's \
position. You are not hostile, and you are not looking for reasons to disallow \
things — you are identifying what a scrutiny would actually ask about.

Flag only:
  - a claim that looks aggressive relative to the taxpayer's stated profile
  - a position stated without the supporting fact that would justify it
  - an inconsistency between two parts of the answer

Do NOT flag:
  - a standard, well-documented, clearly-within-limits claim
  - anything already caveated in the answer
  - the mere fact that a deduction was claimed

A reviewer who flags everything is ignored, and then a genuinely thin claim \
slips past because it looks like all the rest. If nothing here would draw a \
query, return {"findings": []} — that is the expected outcome for most answers.

Respond in JSON:
{"findings": [{"detail": "..."}]}"""


class RiskReviewer:
    """The third pass. Conditional, FLAG-only, except for scope."""

    name = "reviewer_risk"

    def __init__(self, llm: Any | None = None) -> None:
        self._llm = llm

    def applies_to(self, d: DraftUnderReview) -> bool:
        """Scope is always checked; the rest only where a claim is made."""
        return True

    async def review(self, d: DraftUnderReview) -> list[Finding]:
        # Scope first, and it can stop the answer.
        scope = check_scope(d)
        if scope:
            return [scope]

        if not carries_a_claim(d.draft):
            # Informational answer. Skipping here is what keeps the three-pass
            # path inside its latency budget.
            logger.debug("risk pass skipped: no claim asserted")
            return []

        findings: list[Finding] = []
        thin = check_documentation_thin(d)
        if thin:
            findings.append(thin)

        findings.extend(await self._judgement_pass(d))
        return findings

    async def _judgement_pass(self, d: DraftUnderReview) -> list[Finding]:
        if self._llm is None:
            return []
        try:
            resp = await self._llm.complete(
                f"Taxpayer profile: {d.profile}\n\nPosition taken:\n{d.draft}",
                system=RISK_SYSTEM_PROMPT,
                json_mode=True,
                max_tokens=500,
            )
            raw = resp.json()
        except Exception:
            logger.warning("risk judgement pass unavailable; deterministic checks stand")
            return []

        out: list[Finding] = []
        for item in (raw.get("findings") or [])[:3]:
            detail = str(item.get("detail", "")).strip()
            if detail:
                out.append(
                    Finding(
                        Verdict.FLAG, Category.DOCUMENTATION_RISK, detail,
                        reviewer=self.name,
                    )
                )
        return out
