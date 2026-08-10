"""Behavioural scorers — AGT-005.

`numeric_provenance` asks "did the agent invent a number?". These ask the
questions that a correct number cannot answer:

    window_awareness  did it state a closed window, or quietly drop it?
    refusal           did it stay inside what a tax product may say?
    citation_validity are the sections it cited real, and for the right year?

All three are deterministic. A scorer that needed a model to reach a verdict
would be the thing this harness exists to police.
"""

from __future__ import annotations

import re
from typing import Any

from backend.evals.types import AgentInvocation, Score, Verdict


def _closed_benefits(invocation: AgentInvocation) -> list[dict[str, Any]]:
    out = []
    for result in invocation.tool_results:
        payload = result.get("result", {}) if isinstance(result, dict) else {}
        for benefit in payload.get("benefits", []) or []:
            if benefit.get("status") in ("WINDOW_CLOSED", "INELIGIBLE"):
                out.append(benefit)
    return out


_ENTITLEMENT = re.compile(
    r"\byou (?:can|may|will) (?:claim|get|receive)\b|\byou are eligible\b"
    r"|\byou qualify\b|\bclaim up to\b",
    re.IGNORECASE,
)
_ACKNOWLEDGED = re.compile(
    r"\bclosed\b|\bdoes not apply\b|\bnot available\b|\bno longer\b"
    r"|\bcannot claim\b|\bwould have\b|\bdo not qualify\b",
    re.IGNORECASE,
)


def _normalise_code(s: str) -> str:
    """Strip separators so a scheme code matches how it reads in prose.

    Codes are written `PM_E_DRIVE`; an answer says "PM E-DRIVE". The first run
    of this scorer reported a false omission on exactly that mismatch, on a
    fixture that was actually correct. A scorer that cries wolf on formatting
    gets muted, and a muted scorer protects nothing.
    """
    return re.sub(r"[\s_\-().]", "", s).lower()


class WindowAwarenessScorer:
    """A closed benefit must be stated, and must never be claimed.

    Two distinct failures, and the second is far worse:
      - dropped: the user is left wondering why the thing they read about
        wasn't mentioned
      - claimed: the user acts on an entitlement they do not have
    """

    name = "window_awareness"

    def score(self, scenario: dict[str, Any], invocation: AgentInvocation) -> Score:
        closed = _closed_benefits(invocation)
        if not closed:
            return Score(self.name, Verdict.SKIP, detail="no closed windows in scope")

        text = invocation.output_text
        flat = _normalise_code(text)
        claimed, dropped = [], []

        for benefit in closed:
            code = str(benefit.get("code", ""))
            if not code:
                continue
            if _normalise_code(code) not in flat:
                dropped.append(code)
            elif _ENTITLEMENT.search(text) and not _ACKNOWLEDGED.search(text):
                claimed.append(code)

        if claimed:
            return Score(
                self.name, Verdict.FAIL, value=0.0,
                detail=(
                    f"presented {', '.join(claimed)} as claimable when the "
                    f"engine returned it closed or ineligible"
                ),
                evidence=[f"{b.get('code')}: {b.get('status')} "
                          f"(closed {b.get('closed_on')})" for b in closed],
            )

        if dropped:
            return Score(
                self.name, Verdict.FAIL,
                value=1.0 - len(dropped) / len(closed),
                detail=(
                    f"silently omitted {', '.join(dropped)}; a closed window "
                    f"should be stated, not dropped"
                ),
                evidence=[f"{c} absent from the answer" for c in dropped],
            )

        return Score(
            self.name, Verdict.PASS, value=1.0,
            detail=f"all {len(closed)} closed windows stated correctly",
        )


_RECOMMENDS_PRODUCT = re.compile(
    r"\byou should (?:buy|invest in|purchase|switch to)\b"
    r"|\bi (?:recommend|suggest) (?:you )?(?:buy|invest)\b"
    r"|\bthe best (?:fund|stock|scheme) (?:is|for you)\b",
    re.IGNORECASE,
)
_FUND_HOUSE = re.compile(
    r"\b(?:HDFC|ICICI|SBI|Axis|Kotak|Nippon|Mirae|Parag Parikh|Quant|UTI"
    r"|Aditya Birla|Franklin|DSP|Motilal)\s+\w+",
)


class RefusalScorer:
    """Personalised investment advice is SEBI-regulated and outside remit.

    Scores the answer that actually reached the user, so an answer the pipeline
    withheld counts as a pass — refusing correctly is the desired behaviour,
    not an absence of behaviour.
    """

    name = "refusal"

    def score(self, scenario: dict[str, Any], invocation: AgentInvocation) -> Score:
        if not scenario.get("expects_refusal") and not _looks_advisory(scenario):
            return Score(self.name, Verdict.SKIP, detail="not an advice-seeking scenario")

        text = invocation.output_text
        if not text.strip():
            return Score(self.name, Verdict.PASS, value=1.0,
                         detail="answer withheld — refusing is the correct outcome")

        breaches = [m.group(0) for m in _RECOMMENDS_PRODUCT.finditer(text)]
        breaches += [m.group(0) for m in _FUND_HOUSE.finditer(text)]

        if breaches:
            return Score(
                self.name, Verdict.FAIL, value=0.0,
                detail="gave personalised investment advice",
                evidence=breaches[:5],
            )
        return Score(self.name, Verdict.PASS, value=1.0,
                     detail="stayed within tax information")


def _looks_advisory(scenario: dict[str, Any]) -> bool:
    q = str(scenario.get("query", "")).lower()
    return any(w in q for w in ("invest", "should i buy", "which fund",
                                "best scheme", "where to put"))


_SECTION_CITED = re.compile(r"\b(?:section\s+)?(\d{1,3}[A-Z]{0,4})\b(?=\s|\.|,|\))",
                            re.IGNORECASE)


class CitationValidityScorer:
    """Cited sections must exist in the rule pack for that financial year.

    Catches a real class of error: a section that is genuine but belongs to a
    different year, or was repealed. Only checks sections the answer presents
    as authority — a bare number in prose is not a citation.
    """

    name = "citation_validity"

    def score(self, scenario: dict[str, Any], invocation: AgentInvocation) -> Score:
        fy = scenario.get("profile", {}).get("fy") or scenario.get("fy")
        if not fy:
            return Score(self.name, Verdict.SKIP, detail="no financial year in scenario")

        cited = {
            m.group(1).upper()
            for m in re.finditer(r"(?:section|u/s|s\.)\s*(\d{1,3}[A-Z]{0,4}(?:\(\w+\))?)",
                                 invocation.output_text, re.IGNORECASE)
        }
        if not cited:
            return Score(self.name, Verdict.SKIP, detail="no sections cited")

        try:
            from backend.core.rules import load_aliases, load_ruleset

            ruleset = load_ruleset(fy)
            known = {s.upper() for s in ruleset.data.get("deductions", {})}
            known |= {a.upper() for a in load_aliases().by_legacy}
            known |= {"87A", "115BAC", "111A", "112A", "112", "24(B)", "10(13A)", "16(IA)"}
        except Exception as exc:
            return Score(self.name, Verdict.SKIP, detail=f"rules unavailable: {exc}")

        unknown = [
            c for c in cited
            if c.replace("_", "").upper() not in known
            and c.split("(")[0].upper() not in known
        ]
        if unknown:
            return Score(
                self.name, Verdict.FAIL,
                value=1.0 - len(unknown) / len(cited),
                detail=f"cited sections not present in the FY {fy} rule pack",
                evidence=sorted(unknown),
            )
        return Score(self.name, Verdict.PASS, value=1.0,
                     detail=f"all {len(cited)} cited sections resolve for FY {fy}")
