"""Form 16 parser — DOC-001.

Why this matters more than it looks
------------------------------------
Asking someone to type their own salary breakdown is the biggest drop-off in a
tax product, and it is also the biggest source of wrong answers: people guess
their basic pay, forget the professional tax, and confuse gross with CTC. The
figures are already on a document their employer gave them.

Failure policy
--------------
This parser **fails loudly**. It does not guess, it does not interpolate, and
it does not fall back to a default. Every extracted figure carries a confidence
and the source line it came from, and anything below `REVIEW` threshold is
returned as `needs_confirmation` rather than silently entering a calculation.

That is deliberate and slightly annoying by design. A parser that quietly
mis-reads gross salary produces an answer that is confidently, precisely wrong
— the exact failure this rebuild exists to remove. An extraction the user has
to glance at is a far better trade.

Internal consistency is checked, not assumed: the components must sum to the
stated gross, and the parser reports the discrepancy rather than picking
whichever number it likes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any

# ── extraction primitives ───────────────────────────────────────────────────

# Indian-format amounts as they appear in a Form 16: 12,75,000.00 / 1275000 /
# ₹ 12,75,000 / 0.00.
#
# Three alternatives, and the order matters:
#   grouped with commas · anything with a decimal part · three or more digits
#
# The decimal branch exists because the first version required three-plus
# characters, which made "0.00" invisible. A zero-value line then looked like
# an unlabelled one, so the matcher fell through to the NEXT line and returned
# a completely different figure — the exempt-allowances line silently picked up
# gross salary. Zero is a real answer on a Form 16 and must be readable.
#
# Requiring a decimal, a comma, or three digits keeps list markers like "1."
# and "(a)" out.
_AMOUNT = re.compile(
    r"(?:₹|Rs\.?|INR)?\s*"
    r"(\d{1,3}(?:,\d{2,3})+(?:\.\d{1,2})?|\d+\.\d{1,2}|\d{3,})"
)

_PAN = re.compile(r"\b([A-Z]{5}[0-9]{4}[A-Z])\b")
_TAN = re.compile(r"\b([A-Z]{4}[0-9]{5}[A-Z])\b")
_ASSESSMENT_YEAR = re.compile(r"\b(20\d{2})\s*[-–/]\s*(\d{2,4})\b")


class Confidence(str, Enum):  # noqa: UP042
    HIGH = "high"        # matched a canonical label, one unambiguous amount
    REVIEW = "review"    # matched, but ambiguous — show it to the user
    ABSENT = "absent"    # not found; the caller must ask

    @property
    def usable_without_confirmation(self) -> bool:
        return self is Confidence.HIGH


@dataclass(frozen=True, slots=True)
class Field:
    """One extracted value, with where it came from."""

    name: str
    value: Decimal | str | None
    confidence: Confidence
    source_line: str = ""
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": str(self.value) if self.value is not None else None,
            "confidence": self.confidence.value,
            "source_line": self.source_line,
            "note": self.note or None,
        }


class Form16ParseError(Exception):
    """The document is not a Form 16, or is too damaged to read.

    Raised rather than returning a half-filled result: a partially parsed
    document that looks parsed is worse than one that clearly failed.
    """


# ── labels ──────────────────────────────────────────────────────────────────
#
# Employers use different wording for the same line. These are matched in
# order, longest-first, so "gross salary" does not shadow "gross total income".

_LABELS: dict[str, tuple[str, ...]] = {
    "gross_salary": (
        "gross salary",
        "total amount of salary",
        "salary as per provisions contained in section 17(1)",
        "salary u/s 17(1)",
    ),
    "exempt_allowances": (
        "total amount of exemption claimed under section 10",
        "less: allowances to the extent exempt under section 10",
        "exemption claimed under section 10",
    ),
    "standard_deduction": (
        "standard deduction under section 16(ia)",
        "standard deduction",
    ),
    "professional_tax": (
        "tax on employment under section 16(iii)",
        "professional tax",
        "tax on employment",
    ),
    "net_salary": (
        "income chargeable under the head salaries",
        "net salary",
    ),
    "gross_total_income": ("gross total income",),
    "total_deductions_via": (
        "aggregate of deductible amount under chapter vi-a",
        "total deduction under chapter vi-a",
    ),
    "taxable_income": (
        "total taxable income",
        "total income",
    ),
    "tax_payable": (
        "tax payable",
        "net tax payable",
        "total tax payable",
    ),
    "tds_deducted": (
        "total amount of tax deducted at source",
        "amount of tax deducted",
        "tax deducted at source",
    ),
}

# Chapter VI-A lines, captured individually so the profile can be populated
# rather than just totalled.
_DEDUCTION_LABELS: dict[str, tuple[str, ...]] = {
    "80C": ("section 80c", "deduction in respect of life insurance premia"),
    "80CCC": ("section 80ccc",),
    "80CCD_1": ("section 80ccd(1)", "section 80ccd (1)"),
    "80CCD_1B": ("section 80ccd(1b)", "section 80ccd (1b)"),
    "80CCD_2": ("section 80ccd(2)", "section 80ccd (2)"),
    "80D": ("section 80d", "deduction in respect of health insurance"),
    "80E": ("section 80e",),
    "80G": ("section 80g",),
    "80TTA": ("section 80tta",),
    "80U": ("section 80u",),
}


def _all_labels() -> tuple[str, ...]:
    """Every label across every field, longest first."""
    seen: set[str] = set()
    for group in (*_LABELS.values(), *_DEDUCTION_LABELS.values()):
        seen.update(group)
    return tuple(sorted(seen, key=len, reverse=True))


def _a_longer_label_owns(lowered_line: str, label: str) -> bool:
    """True if a more specific label also matches this line.

    Substring shadowing is the classic label-matching bug: "total income"
    matches the "gross total income" line, "gross salary" matches "gross
    salary as per section 17", and so on. The most specific label wins.
    """
    return any(
        other != label and len(other) > len(label) and other in lowered_line
        for other in _all_labels()
    )


def _to_decimal(raw: str) -> Decimal | None:
    try:
        return Decimal(raw.replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        return None


def _amounts_on(line: str) -> list[Decimal]:
    out = []
    for m in _AMOUNT.finditer(line):
        value = _to_decimal(m.group(1))
        # A bare 4-digit number on a Form 16 line is almost always a year.
        if value is not None and not (1900 <= value <= 2100 and "." not in m.group(1)):
            out.append(value)
    return out


def _find_labelled_amount(lines: list[str], labels: tuple[str, ...]) -> Field | None:
    """Find the amount on (or just after) a labelled line.

    Every occurrence of every label is considered, and the most confident match
    wins — not the first one found.

    That matters because a Form 16 uses the same words twice: "1. Gross Salary"
    is a heading with sub-items beneath it, and a few lines later "3. Gross
    Salary  1275000.00" is the total. Taking the first match meant reading the
    sub-item off the following line and grading it REVIEW, when an unambiguous
    figure sat further down. First-match-wins is a layout assumption; preferring
    the confident match is a reading.
    """
    candidates: list[Field] = []

    for label in labels:
        for i, line in enumerate(lines):
            lowered_line = line.lower()
            if label not in lowered_line:
                continue

            # Shadowing guard. "total income" is a substring of "gross total
            # income", so without this the taxable-income label matches the
            # gross-total-income line and returns the wrong figure — which it
            # did, silently, until a fixture caught it.
            #
            # If a LONGER label from any field also matches this line, that
            # label owns it.
            if _a_longer_label_owns(lowered_line, label):
                continue

            amounts = _amounts_on(line)
            if len(amounts) == 1:
                candidates.append(Field(label, amounts[0], Confidence.HIGH, line.strip()))
                continue
            if len(amounts) > 1:
                # Several figures on one row — typically a running total column.
                # The rightmost is conventionally the value, but conventionally
                # is not certainly.
                candidates.append(
                    Field(label, amounts[-1], Confidence.REVIEW, line.strip(),
                          note=f"{len(amounts)} amounts on this line; took the last")
                )
                continue

            # Nothing on the label line — look at the next non-blank.
            for nxt in lines[i + 1 : i + 3]:
                following = _amounts_on(nxt)
                if len(following) == 1:
                    candidates.append(
                        Field(label, following[0], Confidence.REVIEW,
                              f"{line.strip()} | {nxt.strip()}",
                              note="amount taken from the following line")
                    )
                    break

    if not candidates:
        return None

    high = [c for c in candidates if c.confidence is Confidence.HIGH]
    if high:
        # Several confident readings that disagree is itself a finding — a
        # document where "gross salary" appears twice with different figures
        # should be looked at, not silently resolved.
        distinct = {c.value for c in high}
        if len(distinct) > 1:
            return Field(
                high[0].name, high[-1].value, Confidence.REVIEW, high[-1].source_line,
                note=(
                    f"this label appears {len(high)} times with differing amounts "
                    f"({', '.join(str(v) for v in sorted(distinct))}); took the last"
                ),
            )
        return high[0]

    return candidates[0]


# ── result ──────────────────────────────────────────────────────────────────

@dataclass(slots=True)
class Form16:
    """A parsed Form 16, with everything the caller needs to decide whether to
    trust it."""

    assessment_year: str | None = None
    employee_pan: str | None = None
    employer_tan: str | None = None
    fields: dict[str, Field] = field(default_factory=dict)
    deductions: dict[str, Field] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    # ── access ──────────────────────────────────────────────────────────────

    def amount(self, name: str) -> Decimal | None:
        f = self.fields.get(name)
        return f.value if f and isinstance(f.value, Decimal) else None

    @property
    def needs_confirmation(self) -> list[Field]:
        """Everything the user must eyeball before it enters a calculation."""
        return [
            f for f in (*self.fields.values(), *self.deductions.values())
            if not f.confidence.usable_without_confirmation
        ]

    @property
    def missing(self) -> list[str]:
        essential = ("gross_salary", "taxable_income", "tds_deducted")
        return [name for name in essential if name not in self.fields]

    @property
    def is_usable(self) -> bool:
        """Enough was read to be worth showing. Not the same as 'trust it'."""
        return "gross_salary" in self.fields and not self.missing

    # ── consistency ─────────────────────────────────────────────────────────

    def check_internal_consistency(self) -> list[str]:
        """Do the parts add up?

        A Form 16 states both its components and its totals, which means the
        document checks itself. If gross minus exemptions minus deductions does
        not reach the stated net, something was misread — and saying so is far
        better than picking whichever figure looks nicer.
        """
        problems: list[str] = []
        gross = self.amount("gross_salary")
        exempt = self.amount("exempt_allowances") or Decimal(0)
        std = self.amount("standard_deduction") or Decimal(0)
        prof = self.amount("professional_tax") or Decimal(0)
        net = self.amount("net_salary")

        if gross is not None and net is not None:
            expected = gross - exempt - std - prof
            if abs(expected - net) > Decimal("1"):
                problems.append(
                    f"components do not reconcile: gross {gross:,} less exemptions "
                    f"{exempt:,}, standard deduction {std:,} and professional tax "
                    f"{prof:,} gives {expected:,}, but the form states net salary "
                    f"of {net:,} (difference {expected - net:,})"
                )

        claimed = self.amount("total_deductions_via")
        itemised = sum(
            (f.value for f in self.deductions.values() if isinstance(f.value, Decimal)),
            Decimal(0),
        )
        if claimed is not None and itemised and abs(claimed - itemised) > Decimal("1"):
            problems.append(
                f"Chapter VI-A lines sum to {itemised:,} but the form states "
                f"{claimed:,} (difference {claimed - itemised:,})"
            )

        return problems

    def to_dict(self) -> dict[str, Any]:
        return {
            "assessment_year": self.assessment_year,
            "employee_pan": self.employee_pan,
            "employer_tan": self.employer_tan,
            "fields": {k: v.to_dict() for k, v in self.fields.items()},
            "deductions": {k: v.to_dict() for k, v in self.deductions.items()},
            "warnings": self.warnings,
            "needs_confirmation": [f.name for f in self.needs_confirmation],
            "missing": self.missing,
            "is_usable": self.is_usable,
        }

    def to_profile_draft(self) -> dict[str, Any]:
        """A profile the user confirms — never one that is applied silently.

        Only HIGH-confidence figures are included. Anything else appears in
        `needs_confirmation` and must be resolved by asking.
        """
        draft: dict[str, Any] = {}
        if (g := self.fields.get("gross_salary")) and g.confidence.usable_without_confirmation:
            draft["salary"] = str(g.value)
        if (t := self.fields.get("tds_deducted")) and t.confidence.usable_without_confirmation:
            draft["taxes_paid"] = str(t.value)

        deductions = {
            code: str(f.value)
            for code, f in self.deductions.items()
            if f.confidence.usable_without_confirmation and isinstance(f.value, Decimal)
        }
        if deductions:
            draft["deductions"] = deductions
        if self.employee_pan:
            draft["pan"] = self.employee_pan
        return draft


# ── entry points ────────────────────────────────────────────────────────────

def parse_text(text: str) -> Form16:
    """Parse already-extracted text. The unit-testable half."""
    if not text or not text.strip():
        raise Form16ParseError("empty document")

    lowered = text.lower()
    has_heading = "form no. 16" in lowered or "form 16" in lowered
    # Some employers strip the heading when exporting Part B alone, so a
    # recognisable structure is accepted as an alternative.
    has_structure = "chapter vi-a" in lowered or "tax deducted at source" in lowered

    if not has_heading and not has_structure:
        raise Form16ParseError(
            "this does not look like a Form 16 — no recognisable heading or "
            "salary/TDS structure found. Refusing to parse rather than "
            "returning figures scraped from an unknown document."
        )

    lines = [ln for ln in text.splitlines() if ln.strip()]
    form = Form16()

    if m := _ASSESSMENT_YEAR.search(text):
        end = m.group(2)
        form.assessment_year = f"{m.group(1)}-{end[-2:]}"
    if m := _PAN.search(text):
        form.employee_pan = m.group(1)
    if m := _TAN.search(text):
        form.employer_tan = m.group(1)

    for name, labels in _LABELS.items():
        if found := _find_labelled_amount(lines, labels):
            form.fields[name] = Field(
                name, found.value, found.confidence, found.source_line, found.note
            )

    for code, labels in _DEDUCTION_LABELS.items():
        if found := _find_labelled_amount(lines, labels):
            form.deductions[code] = Field(
                code, found.value, found.confidence, found.source_line, found.note
            )

    form.warnings.extend(form.check_internal_consistency())
    for name in form.missing:
        form.warnings.append(f"could not find {name.replace('_', ' ')}")

    return form


def parse_pdf(path: str) -> Form16:
    """Parse a Form 16 PDF.

    Text extraction is separated from interpretation so the parsing logic is
    testable without a PDF, and a text-extraction failure is distinguishable
    from a document that simply is not a Form 16.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise Form16ParseError(
            "PyMuPDF is not installed, so PDFs cannot be read."
        ) from exc

    try:
        with fitz.open(path) as doc:
            text = "\n".join(page.get_text() for page in doc)
    except Exception as exc:
        raise Form16ParseError(f"could not read the PDF: {exc}") from exc

    if not text.strip():
        raise Form16ParseError(
            "no text could be extracted. This is probably a scanned image; OCR "
            "would be needed, and guessing at figures from an unreadable "
            "document is not something this parser will do."
        )

    return parse_text(text)
