"""The keystone scorer.

Extracts every number from an agent's user-facing output and fails if that
number cannot be traced to the tool results the agent was given.

This is what makes the project's governing rule mechanical:

    No rupee figure shown to a user may originate from a language model.

A model asked to "explain" a tax computation will happily produce arithmetic
that is internally plausible and factually invented. Prompting does not fix
that reliably. A hard gate does.

Design notes
------------
Precision matters in both directions. A scorer that fires on section numbers
and financial years would be turned off within a week, and a scorer that is
turned off protects nothing. So:

  * Money-shaped and large numbers must be traceable.
  * Structural numbers — section references, financial years, dates, list
    ordinals, small counts — are recognised and exempt.
  * Comparison is tolerant of formatting (Indian digit grouping, ₹, lakh/crore
    shorthand) and of rounding to the rupee.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from typing import Any

from backend.evals.types import AgentInvocation, Score, Verdict

# ── Structural numbers that are never money ─────────────────────────────────

# Section references. The prefix is NOT optional unless the number carries a
# letter suffix or a parenthesised sub-clause — otherwise a pattern like
# "80C" generalises to "any two-digit number" and silently masks real money.
# That bug let a fabricated ₹46,800 through on first run.
_SECTION = re.compile(
    r"(?:"
    r"(?:section|u/s|sec\.?|s\.)\s*\d{1,3}[A-Z]{0,4}(?:\s*\(\s*[0-9ivxa-z]+\s*\))*"
    r"|"
    r"\b\d{1,3}[A-Z]{1,5}(?:\s*\(\s*[0-9ivxa-z]+\s*\))*"   # 80C, 87A, 115BAC
    r"|"
    r"\b\d{1,3}\s*\(\s*[0-9ivxa-z]{1,4}\s*\)"              # 24(b), 10(13A)
    r")",
    re.IGNORECASE,
)
# Financial / assessment years: 2026-27, FY 2026-27, AY 2027-28.
# The en dash is deliberate — agents and source documents both use it.
_FY = re.compile(r"\b(?:FY|AY)?\s*20\d{2}\s*[-–/]\s*\d{2,4}\b", re.IGNORECASE)
# Dates: 31 March 2026, 2026-03-31, 31/03/2026
_DATE = re.compile(
    r"\b(?:\d{1,2}[\s/-](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
    r"[a-z]*[\s/-]\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})\b",
    re.IGNORECASE,
)
# ITR-1, ITR-4, Form 16, Form 26AS
_FORM = re.compile(r"\b(?:ITR|Form)\s*-?\s*\d+[A-Z]{0,3}\b", re.IGNORECASE)

_STRUCTURAL = (_SECTION, _FY, _DATE, _FORM)

# A bare integer at or below this is treated as a count/ordinal, not money
# ("3 deductions", "2 employers"). Anything larger must be traceable.
_SMALL_COUNT_MAX = 100

# Candidate number, optionally ₹-prefixed, with Indian or Western grouping,
# optional decimals, optional lakh/crore/L/Cr suffix.
#
# The grouped branch requires at least ONE comma (`+`, not `*`). With `*` the
# alternation matched the first three digits of an ungrouped number and
# stopped: "1275000.00" in a tool result became 127, so the scorer decided a
# correct ₹12,75,000 in the answer was unsupported. A keystone check producing
# false accusations of fabrication is worse than no check — it trains people to
# override it.
_NUMBER = re.compile(
    r"(?P<currency>₹|Rs\.?|INR)?\s*"
    r"(?P<num>\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"\s*(?P<scale>lakhs?|lacs?|crores?|cr|L\b)?",
    re.IGNORECASE,
)

_SCALE = {
    "lakh": Decimal(100_000), "lakhs": Decimal(100_000),
    "lac": Decimal(100_000), "lacs": Decimal(100_000), "l": Decimal(100_000),
    "crore": Decimal(10_000_000), "crores": Decimal(10_000_000),
    "cr": Decimal(10_000_000),
}


def _mask_structural(text: str) -> str:
    """Blank out structural numbers so they are never treated as money."""
    for pattern in _STRUCTURAL:
        text = pattern.sub(lambda m: " " * len(m.group(0)), text)
    return text


def _to_decimal(raw: str, scale: str | None) -> Decimal | None:
    try:
        value = Decimal(raw.replace(",", ""))
    except InvalidOperation:
        return None
    if scale:
        value *= _SCALE.get(scale.lower().rstrip("."), Decimal(1))
    return value


def extract_claimed_numbers(text: str) -> list[tuple[Decimal, str]]:
    """Numbers the agent asserted to the user, with the phrase around each."""
    masked = _mask_structural(text)
    found: list[tuple[Decimal, str]] = []

    for m in _NUMBER.finditer(masked):
        value = _to_decimal(m.group("num"), m.group("scale"))
        if value is None:
            continue

        explicit_money = bool(m.group("currency")) or bool(m.group("scale"))
        # Bare small integers are counts, not money.
        if not explicit_money and value <= _SMALL_COUNT_MAX and value == value.to_integral_value():
            continue
        # Bare percentages are rates; they are checked by citation_validity.
        tail = masked[m.end():m.end() + 1]
        if not explicit_money and tail == "%":
            continue

        start = max(0, m.start() - 40)
        found.append((value, " ".join(masked[start:m.end() + 20].split())))

    return found


def _numbers_in(obj: Any) -> Iterable[Decimal]:
    """Every numeric value anywhere in a tool-result payload."""
    if isinstance(obj, bool):
        return
    if isinstance(obj, int | float | Decimal):
        yield Decimal(str(obj))
    elif isinstance(obj, str):
        for m in _NUMBER.finditer(obj):
            value = _to_decimal(m.group("num"), m.group("scale"))
            if value is not None:
                yield value
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _numbers_in(v)
    elif isinstance(obj, list | tuple | set):
        for v in obj:
            yield from _numbers_in(v)


def _traceable(claimed: Decimal, grounded: set[Decimal]) -> bool:
    """Allow formatting and rupee-rounding differences, nothing more."""
    if claimed in grounded:
        return True
    for g in grounded:
        if abs(g - claimed) <= Decimal("0.5"):
            return True
        # An agent rounding ₹60,432 to "about ₹60,000" is acceptable; a
        # fabricated ₹1,50,000 is not. Only round-number restatements pass.
        if claimed % 1000 == 0 and claimed != 0 and abs(g - claimed) < 1000:
            return True
    return False


class NumericProvenanceScorer:
    """Fails when the agent states a figure the tools never produced."""

    name = "numeric_provenance"

    def score(
        self,
        scenario: dict[str, Any],
        invocation: AgentInvocation,
    ) -> Score:
        if invocation.error:
            return Score(self.name, Verdict.SKIP, detail=f"agent errored: {invocation.error}")

        grounded = set(_numbers_in(invocation.tool_results))
        # Numbers the user supplied are legitimate to quote back.
        grounded |= set(_numbers_in(invocation.profile))

        claimed = extract_claimed_numbers(invocation.output_text)
        if not claimed:
            return Score(self.name, Verdict.PASS, value=1.0,
                         detail="no numeric claims in output")

        untraced = [(v, ctx) for v, ctx in claimed if not _traceable(v, grounded)]

        if untraced:
            return Score(
                self.name,
                Verdict.FAIL,
                value=1.0 - len(untraced) / len(claimed),
                detail=(
                    f"{len(untraced)} of {len(claimed)} numeric claims are not "
                    f"present in any tool result — the model invented them"
                ),
                evidence=[f"{v:,} — \"…{ctx}…\"" for v, ctx in untraced[:10]],
            )

        return Score(
            self.name,
            Verdict.PASS,
            value=1.0,
            detail=f"all {len(claimed)} numeric claims traced to tool output",
        )
