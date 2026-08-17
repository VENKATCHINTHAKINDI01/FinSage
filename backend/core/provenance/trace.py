"""The calculation trace — EVD-001.

Every engine function returns `(value, trace)`. The trace is not logging and
not optional: it is the worksheet shown to the user, and it must reproduce the
value when replayed.

Why replay matters
------------------
The obvious way to "show the working" is to ask a model to explain the number.
That produces arithmetic which is plausible and may be entirely fictional — the
explanation and the computation are two different things that merely tend to
agree.

Here they are the same object. `trace.replay()` re-executes the recorded
operations from the recorded operands and must return the recorded result.
A golden test asserts it. If the worksheet and the answer ever diverge, the
build fails rather than the user being misled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any

from backend.core.provenance.citation import Citation
from backend.core.provenance.money import ZERO, Money


class Op(str, Enum):
    """Operations a trace step can record.

    Deliberately small. Every tax computation decomposes into these, and a
    closed set is what makes replay possible.
    """

    LITERAL = "literal"        # a given: an input, or a rule constant
    SUM = "sum"                # Σ operands
    SUBTRACT = "subtract"      # operands[0] − operands[1] − …
    MULTIPLY = "multiply"      # operands[0] × factor
    MIN = "min"
    MAX = "max"
    SLAB = "slab"             # progressive slab application (children carry bands)
    CLAMP_ZERO = "clamp_zero"  # max(operand, 0) — tax is never negative
    ROUND = "round"            # statutory rounding (288A / 288B)


@dataclass(frozen=True, slots=True)
class Step:
    """One line of the worksheet."""

    label: str
    op: Op
    result: Money
    operands: tuple[Money, ...] = ()
    factor: Decimal | None = None       # for MULTIPLY
    citation: Citation | None = None
    note: str = ""
    children: tuple[Step, ...] = ()

    # ── replay ──────────────────────────────────────────────────────────────

    def recompute(self) -> Money:
        """Re-derive this step's result from its own operands."""
        if self.op is Op.LITERAL:
            return self.result

        if self.op is Op.SUM:
            total = ZERO
            for o in self.operands:
                total = total + o
            return total

        if self.op is Op.SUBTRACT:
            if not self.operands:
                return ZERO
            total = self.operands[0]
            for o in self.operands[1:]:
                total = total - o
            return total

        if self.op is Op.MULTIPLY:
            if self.factor is None or len(self.operands) != 1:
                raise ValueError(f"{self.label}: MULTIPLY needs one operand and a factor")
            return self.operands[0] * self.factor

        if self.op is Op.MIN:
            return min(self.operands)

        if self.op is Op.MAX:
            return max(self.operands)

        if self.op is Op.CLAMP_ZERO:
            return self.operands[0].clamp_non_negative()

        if self.op is Op.SLAB:
            # The bands are the children; the result is their sum.
            total = ZERO
            for c in self.children:
                total = total + c.result
            return total

        if self.op is Op.ROUND:
            # Rounding is not re-derivable from operands alone (288A vs 288B
            # differ only by intent), so the note records which applied and the
            # recorded result stands.
            return self.result

        raise ValueError(f"unknown operation: {self.op}")

    def verify(self) -> list[str]:
        """Depth-first check that every step reproduces its own result."""
        problems: list[str] = []
        for child in self.children:
            problems.extend(child.verify())
        try:
            got = self.recompute()
        except Exception as exc:
            problems.append(f"{self.label}: replay raised {exc!r}")
            return problems
        if got != self.result:
            problems.append(
                f"{self.label}: worksheet says {self.result}, replay gives {got}"
            )
        return problems

    # ── rendering ───────────────────────────────────────────────────────────

    def render(self, indent: int = 0, width: int = 52) -> list[str]:
        pad = "  " * indent
        left = f"{pad}{self.label}"
        line = f"{left:<{width}}{self.result!s:>16}"
        # Both, when both are present. These were once an if/elif, which meant
        # attaching a citation to a step silently deleted its explanation from
        # the worksheet — and the steps most worth citing are exactly the ones
        # whose reasoning a reader needs (a rebate that vanished, a proviso
        # that denied interest, a deduction disallowed by regime).
        if self.citation:
            line += f"   [{self.citation.display}]"
        if self.note:
            line += f"   ({self.note})"
        out = [line]
        for child in self.children:
            out.extend(child.render(indent + 1, width))
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "op": self.op.value,
            "result": self.result.to_json(),
            "operands": [o.to_json() for o in self.operands],
            "factor": str(self.factor) if self.factor is not None else None,
            "citation": self.citation.to_dict() if self.citation else None,
            "note": self.note or None,
            "children": [c.to_dict() for c in self.children],
        }


@dataclass(slots=True)
class Trace:
    """An ordered worksheet of steps producing one final value."""

    title: str
    steps: list[Step] = field(default_factory=list)

    # ── recording ───────────────────────────────────────────────────────────

    def add(self, step: Step) -> Money:
        self.steps.append(step)
        return step.result

    def literal(
        self,
        label: str,
        value: Money,
        *,
        citation: Citation | None = None,
        note: str = "",
    ) -> Money:
        return self.add(Step(label, Op.LITERAL, value, citation=citation, note=note))

    def sum_of(self, label: str, *values: Money, note: str = "") -> Money:
        total = ZERO
        for v in values:
            total = total + v
        return self.add(Step(label, Op.SUM, total, operands=values, note=note))

    def subtract(
        self,
        label: str,
        base: Money,
        *deductions: Money,
        citation: Citation | None = None,
        note: str = "",
    ) -> Money:
        result = base
        for d in deductions:
            result = result - d
        return self.add(
            Step(label, Op.SUBTRACT, result, operands=(base, *deductions),
                 citation=citation, note=note)
        )

    def multiply(
        self,
        label: str,
        base: Money,
        factor: Decimal,
        *,
        citation: Citation | None = None,
        note: str = "",
    ) -> Money:
        return self.add(
            Step(label, Op.MULTIPLY, base * factor, operands=(base,), factor=factor,
                 citation=citation, note=note)
        )

    def lesser_of(
        self,
        label: str,
        *values: Money,
        citation: Citation | None = None,
        note: str = "",
    ) -> Money:
        return self.add(
            Step(label, Op.MIN, min(values), operands=values,
                 citation=citation, note=note)
        )

    def greater_of(self, label: str, *values: Money, note: str = "") -> Money:
        return self.add(Step(label, Op.MAX, max(values), operands=values, note=note))

    def clamp_zero(self, label: str, value: Money, *, note: str = "") -> Money:
        return self.add(
            Step(label, Op.CLAMP_ZERO, value.clamp_non_negative(),
                 operands=(value,), note=note)
        )

    def slab(self, label: str, bands: list[Step], *, citation: Citation | None = None) -> Money:
        total = ZERO
        for b in bands:
            total = total + b.result
        return self.add(
            Step(label, Op.SLAB, total, children=tuple(bands), citation=citation)
        )

    def rounded(self, label: str, value: Money, rounded: Money, *, note: str) -> Money:
        return self.add(
            Step(label, Op.ROUND, rounded, operands=(value,), note=note)
        )

    def nest(self, label: str, inner: Trace, result: Money, *, note: str = "") -> Money:
        """Fold a sub-computation in as one collapsible line."""
        return self.add(
            Step(label, Op.SUM, result, operands=(result,),
                 children=tuple(inner.steps), note=note)
        )

    # ── use ─────────────────────────────────────────────────────────────────

    @property
    def result(self) -> Money:
        return self.steps[-1].result if self.steps else ZERO

    def replay(self) -> Money:
        """Re-execute the worksheet. Must equal the recorded final value."""
        problems = self.verify()
        if problems:
            raise AssertionError(
                "trace does not replay to its own result:\n  "
                + "\n  ".join(problems)
            )
        return self.result

    def verify(self) -> list[str]:
        return [p for s in self.steps for p in s.verify()]

    def citations(self) -> list[Citation]:
        seen: list[Citation] = []

        def walk(step: Step) -> None:
            if step.citation and step.citation not in seen:
                seen.append(step.citation)
            for c in step.children:
                walk(c)

        for s in self.steps:
            walk(s)
        return seen

    def render(self) -> str:
        lines = [self.title, "─" * 68]
        for s in self.steps:
            lines.extend(s.render())
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "result": self.result.to_json(),
            "steps": [s.to_dict() for s in self.steps],
            "citations": [c.to_dict() for c in self.citations()],
        }

    def __str__(self) -> str:
        return self.render()
