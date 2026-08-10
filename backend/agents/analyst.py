"""Analyst — the drafting pass. AGT-008.

Drafts to the standard a chartered accountant applies advising a client, and
computes nothing. Every figure it states was produced by `backend/core` and
handed to it in a tool result.

The prompt is the enforcement's first line and the weakest one; the real
enforcement is `numeric_provenance`, which fails CI if any number in the draft
is absent from the tool results. Both exist because prompting alone does not
reliably stop a model doing arithmetic — it stops it *most* of the time, and
most of the time is not a standard you can apply to someone's tax return.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


ANALYST_SYSTEM_PROMPT = """You are a chartered accountant in India advising a \
client for FY 2026-27 under the Income-tax Act, 2025.

ABSOLUTE RULE: you may not perform arithmetic. Every rupee figure you state \
must appear verbatim in the TOOL RESULTS given to you. Do not add, subtract, \
scale, annualise, or estimate anything. If a number you want is not in the \
tool results, say you could not determine it and name what is missing.

You are writing to a person, not producing a report:
  - lead with the answer, then the reasoning
  - explain WHY a figure is what it is, citing the section
  - if a benefit's window has closed, SAY SO with the closing date — silence \
reads as "there was nothing here"
  - state assumptions plainly and label them as assumptions
  - if something material was never provided, ask for it

Do not recommend specific investment products, funds or shares. Explaining the \
tax treatment of a category is fine; telling someone what to buy is regulated \
advice and outside your remit.

Never claim certainty you do not have. "Based on the figures you gave me" is \
honest; "you will save ₹50,000" when it depends on a document they have not \
produced is not."""


@dataclass(slots=True)
class AnalystRequest:
    query: str
    profile: dict[str, Any]
    fy: str
    regime: str = "new"
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    revision_note: str = ""   # set on a redraft, from the blocking finding


@dataclass(slots=True)
class AnalystDraft:
    text: str
    tool_results: list[dict[str, Any]]
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "latency_ms": self.latency_ms,
            "error": self.error,
        }


def render_tool_results(results: list[dict[str, Any]]) -> str:
    """Present tool output to the model.

    Rendered as explicit labelled facts rather than raw JSON, because a model
    handed JSON tends to treat it as data to compute over, and handed labelled
    statements tends to treat it as facts to report. Small framing difference,
    measurably fewer invented figures.
    """
    import json

    if not results:
        return "(no tool results — you cannot state any figure)"

    lines = ["THESE ARE THE ONLY FIGURES YOU MAY USE:", ""]
    for r in results:
        tool = r.get("tool", "tool")
        if not r.get("success", True):
            lines.append(f"[{tool}] FAILED: {r.get('error', 'unknown')}")
            continue
        lines.append(f"[{tool}]")
        lines.append(json.dumps(r.get("result", {}), indent=2, ensure_ascii=False))
        lines.append("")
    return "\n".join(lines)


class Analyst:
    """Drafts the answer. Has no arithmetic authority."""

    name = "analyst"

    def __init__(self, llm: Any | None = None) -> None:
        self._llm = llm

    async def draft(self, req: AnalystRequest) -> AnalystDraft:
        if self._llm is None:
            return AnalystDraft(
                text="", tool_results=req.tool_results,
                error="no model configured",
            )

        parts = [
            f"Client question: {req.query}",
            "",
            f"Financial year: {req.fy}    Regime: {req.regime}",
            "",
            render_tool_results(req.tool_results),
        ]
        if req.revision_note:
            parts += [
                "",
                "YOUR PREVIOUS DRAFT WAS REJECTED IN REVIEW:",
                req.revision_note,
                "",
                "Address this directly. Do not restate the same claim in softer "
                "language — if the review says a benefit is unavailable, the "
                "redraft must not present it as available.",
            ]

        try:
            resp = await self._llm.complete(
                "\n".join(parts),
                system=ANALYST_SYSTEM_PROMPT,
                max_tokens=1200,
            )
        except Exception as exc:
            logger.warning("analyst draft failed: %s", exc)
            return AnalystDraft(
                text="", tool_results=req.tool_results, error=str(exc)
            )

        return AnalystDraft(
            text=resp.text.strip(),
            tool_results=req.tool_results,
            prompt_tokens=resp.prompt_tokens,
            completion_tokens=resp.completion_tokens,
            latency_ms=resp.latency_ms,
        )
