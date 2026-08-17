"""AIS / TIS reconciliation — DOC-003.

The single highest-value feature in Indian personal tax, and v1 had nothing
touching it.

The Annual Information Statement is the department's own record of what it
believes you earned — reported to it by your employer, your banks, your broker,
the registrar who handled your property sale. An ITR that disagrees with the
AIS is the most common trigger for a notice, and the taxpayer usually finds out
months later.

Reconciling *before* filing turns a future notice into a present decision.

The asymmetry that shapes this module
--------------------------------------
The two directions of mismatch are not equally serious:

  income in AIS but NOT in your return   → the department sees under-reporting
  income in your return but NOT in AIS   → usually harmless, occasionally a
                                            sign you double-counted

So a false negative on the first kind is the failure that matters. Where the
matcher is unsure, it reports rather than resolves — an unnecessary review is
an inconvenience; a missed under-report is a notice.

AIS is not gospel
-----------------
It genuinely does contain errors: sales double-counted across brokers, gross
figures where net is taxable, entries belonging to a joint holder, the same
transaction reported by two parties. That is why the portal has a feedback
mechanism. This module therefore says "these disagree, here is why that might
be legitimate", never "you under-reported".
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any


class Category(str, Enum):
    """AIS information categories, as the portal groups them."""

    SALARY = "salary"
    INTEREST_SAVINGS = "interest_savings"
    INTEREST_DEPOSITS = "interest_deposits"
    DIVIDEND = "dividend"
    SECURITIES = "sale_of_securities"
    MUTUAL_FUNDS = "sale_of_mutual_funds"
    IMMOVABLE_PROPERTY = "sale_of_immovable_property"
    RENT = "rent_received"
    BUSINESS_RECEIPTS = "business_receipts"
    FOREIGN_REMITTANCE = "foreign_remittance"
    TDS = "tax_deducted"
    OTHER = "other"

    @property
    def is_income(self) -> bool:
        """TDS is a credit, not income. Reconciling it as income would double
        count and produce a nonsense mismatch."""
        return self is not Category.TDS

    @property
    def label(self) -> str:
        return self.value.replace("_", " ")


class Severity(str, Enum):
    HIGH = "high"        # AIS reports income the return does not
    MEDIUM = "medium"    # both present, materially different
    LOW = "low"          # return exceeds AIS, or a small difference
    INFO = "info"        # matched

    @property
    def blocks_filing(self) -> bool:
        return self is Severity.HIGH


_CATEGORY_HINTS: dict[Category, tuple[str, ...]] = {
    Category.SALARY: ("salary", "salaries"),
    Category.INTEREST_SAVINGS: ("savings bank interest", "interest from savings"),
    Category.INTEREST_DEPOSITS: ("interest from deposit", "term deposit",
                                 "fixed deposit", "recurring deposit"),
    Category.DIVIDEND: ("dividend",),
    Category.SECURITIES: ("sale of securities", "sale of equity",
                          "off market debit", "securities transaction"),
    Category.MUTUAL_FUNDS: ("mutual fund", "sale of units", "redemption of units"),
    Category.IMMOVABLE_PROPERTY: ("sale of immovable property", "immovable property"),
    Category.RENT: ("rent received", "rental income", "receipt of rent"),
    Category.BUSINESS_RECEIPTS: ("business receipts", "gst turnover",
                                 "receipts from business"),
    Category.FOREIGN_REMITTANCE: ("foreign remittance", "outward remittance"),
    Category.TDS: ("tax deducted", "tds", "tax collected", "tcs"),
}


class AISParseError(Exception):
    """The statement could not be read."""


def classify(description: str) -> Category:
    lowered = description.lower()
    # Longest hint first, so "interest from deposit" beats a bare "interest".
    ordered = sorted(
        ((cat, hint) for cat, hints in _CATEGORY_HINTS.items() for hint in hints),
        key=lambda pair: len(pair[1]),
        reverse=True,
    )
    for category, hint in ordered:
        if hint in lowered:
            return category
    return Category.OTHER


def _to_decimal(raw: Any) -> Decimal | None:
    if raw is None:
        return None
    if isinstance(raw, int | Decimal):
        return Decimal(str(raw))
    cleaned = re.sub(r"[₹,\s]|Rs\.?|INR", "", str(raw), flags=re.IGNORECASE)
    if not cleaned or cleaned in {"-", "--"}:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


# ── parsed statement ────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class AISEntry:
    category: Category
    amount: Decimal
    description: str
    source: str = ""          # the reporting entity, e.g. the bank or employer
    fy: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.value,
            "amount": str(self.amount),
            "description": self.description,
            "source": self.source,
        }


@dataclass(slots=True)
class AIS:
    fy: str | None = None
    pan: str | None = None
    entries: list[AISEntry] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def total_for(self, category: Category) -> Decimal:
        return sum(
            (e.amount for e in self.entries if e.category is category), Decimal(0)
        )

    def by_category(self) -> dict[Category, Decimal]:
        out: dict[Category, Decimal] = {}
        for e in self.entries:
            out[e.category] = out.get(e.category, Decimal(0)) + e.amount
        return out

    def sources_for(self, category: Category) -> list[str]:
        return [e.source for e in self.entries if e.category is category and e.source]


def parse_ais_json(payload: str | dict[str, Any]) -> AIS:
    """Parse the AIS JSON download from the compliance portal.

    The portal's export nests entries under information categories. Structure
    varies between download versions, so this walks the tree looking for
    amount-bearing leaves rather than assuming a fixed path — and reports what
    it could not interpret instead of dropping it.
    """
    data = json.loads(payload) if isinstance(payload, str) else payload
    if not isinstance(data, dict):
        raise AISParseError("AIS payload is not an object")

    ais = AIS(
        fy=data.get("financialYear") or data.get("fy"),
        pan=data.get("pan") or data.get("PAN"),
    )

    def walk(node: Any, inherited_description: str = "") -> None:
        if isinstance(node, dict):
            description = str(
                node.get("informationDescription")
                or node.get("description")
                or node.get("infoDescription")
                or inherited_description
            )
            amount = _to_decimal(
                node.get("amount")
                or node.get("informationValue")
                or node.get("value")
            )
            if amount is not None and description:
                ais.entries.append(
                    AISEntry(
                        category=classify(description),
                        amount=amount,
                        description=description,
                        source=str(node.get("informationSource")
                                   or node.get("source") or ""),
                        fy=ais.fy,
                    )
                )
                return
            for value in node.values():
                walk(value, description)
        elif isinstance(node, list):
            for item in node:
                walk(item, inherited_description)

    walk(data)

    if not ais.entries:
        raise AISParseError(
            "no information entries found. This does not look like an AIS "
            "download — refusing to report a clean reconciliation against an "
            "empty statement, which would be worse than failing."
        )

    unknown = [e for e in ais.entries if e.category is Category.OTHER]
    if unknown:
        ais.warnings.append(
            f"{len(unknown)} entr{'y' if len(unknown) == 1 else 'ies'} could not "
            f"be categorised and are excluded from matching: "
            + "; ".join(e.description[:50] for e in unknown[:3])
        )

    return ais


# ── reconciliation ──────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class Finding:
    category: Category
    severity: Severity
    ais_amount: Decimal
    declared_amount: Decimal
    message: str
    action: str
    benign_explanations: tuple[str, ...] = ()

    @property
    def difference(self) -> Decimal:
        return self.ais_amount - self.declared_amount

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.value,
            "severity": self.severity.value,
            "ais_amount": str(self.ais_amount),
            "declared_amount": str(self.declared_amount),
            "difference": str(self.difference),
            "message": self.message,
            "action": self.action,
            "benign_explanations": list(self.benign_explanations),
        }


# Reasons a disagreement can be legitimate. Shown alongside every finding,
# because AIS is a record of what was *reported*, not a determination of what
# is taxable — and a tool that treats it as gospel will frighten people into
# over-declaring.
_BENIGN: dict[Category, tuple[str, ...]] = {
    Category.SECURITIES: (
        "AIS reports sale CONSIDERATION; your return declares the GAIN. These "
        "are different numbers and a difference here is expected.",
        "the same trade can be reported by more than one intermediary",
    ),
    Category.MUTUAL_FUNDS: (
        "AIS reports redemption value, not gain",
        "SIP redemptions are often reported in aggregate",
    ),
    Category.INTEREST_DEPOSITS: (
        "interest may be reported on accrual while you declare on receipt",
        "a joint account is often reported in full against the first holder",
    ),
    Category.IMMOVABLE_PROPERTY: (
        "a jointly owned property is reported at full value against each owner",
        "AIS reports consideration or stamp duty value, not the capital gain",
    ),
    Category.RENT: (
        "AIS reports gross rent; your return declares net annual value after "
        "the 30% standard deduction and municipal taxes",
    ),
    Category.DIVIDEND: (
        "dividend may be reported gross of TDS",
    ),
}

# Below this, a difference is rounding or a reporting convention, not a finding.
MATERIALITY = Decimal("100")


@dataclass(slots=True)
class Reconciliation:
    fy: str | None
    findings: list[Finding] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def high(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.HIGH]

    @property
    def needs_attention(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is not Severity.INFO]

    @property
    def is_clean(self) -> bool:
        return not self.needs_attention

    def summary(self) -> str:
        if self.is_clean:
            return "Your declared income agrees with the AIS on every category."
        if self.high:
            return (
                f"{len(self.high)} categor{'y' if len(self.high) == 1 else 'ies'} "
                f"appear in the AIS but not in what you have declared. This is "
                f"the most common trigger for a notice — resolve it before filing."
            )
        return f"{len(self.needs_attention)} difference(s) worth checking before filing."

    def to_dict(self) -> dict[str, Any]:
        return {
            "fy": self.fy,
            "is_clean": self.is_clean,
            "summary": self.summary(),
            "high_severity": len(self.high),
            "findings": [f.to_dict() for f in self.findings],
            "warnings": self.warnings,
        }


def reconcile(
    ais: AIS,
    declared: dict[Category | str, Decimal | int | str],
    *,
    materiality: Decimal = MATERIALITY,
) -> Reconciliation:
    """Compare the AIS against what the taxpayer has declared.

    `declared` maps a category to the amount in the return. A category absent
    from `declared` is treated as NOT DECLARED — not as zero-and-therefore-fine.
    That distinction is the whole point: silence is exactly the case that
    produces a notice.
    """
    normalised: dict[Category, Decimal] = {}
    for key, value in declared.items():
        category = key if isinstance(key, Category) else Category(str(key))
        amount = _to_decimal(value)
        if amount is not None:
            normalised[category] = amount

    result = Reconciliation(fy=ais.fy, warnings=list(ais.warnings))

    for category, ais_total in sorted(ais.by_category().items(), key=lambda kv: kv[0].value):
        if not category.is_income:
            continue   # TDS is a credit, not income
        if category is Category.OTHER:
            continue   # already reported as uncategorised

        declared_amount = normalised.get(category)
        benign = _BENIGN.get(category, ())
        sources = ais.sources_for(category)
        source_note = f" (reported by {', '.join(sorted(set(sources))[:3])})" if sources else ""

        if declared_amount is None:
            # The dangerous direction. Never softened.
            result.findings.append(
                Finding(
                    category=category,
                    severity=Severity.HIGH,
                    ais_amount=ais_total,
                    declared_amount=Decimal(0),
                    message=(
                        f"The AIS shows ₹{ais_total:,.0f} of {category.label}"
                        f"{source_note}, and your return declares none."
                    ),
                    action=(
                        f"Either include this {category.label} in your return, or "
                        f"submit feedback on the AIS portal explaining why it does "
                        f"not apply to you. Do not simply ignore it."
                    ),
                    benign_explanations=benign,
                )
            )
            continue

        difference = ais_total - declared_amount
        if abs(difference) <= materiality:
            result.findings.append(
                Finding(category, Severity.INFO, ais_total, declared_amount,
                        f"{category.label.capitalize()} agrees with the AIS.",
                        "nothing to do")
            )
        elif difference > 0:
            result.findings.append(
                Finding(
                    category, Severity.MEDIUM, ais_total, declared_amount,
                    message=(
                        f"The AIS shows ₹{ais_total:,.0f} of {category.label}"
                        f"{source_note} but you have declared ₹{declared_amount:,.0f} "
                        f"— ₹{difference:,.0f} less."
                    ),
                    action="Reconcile the difference, or submit AIS feedback.",
                    benign_explanations=benign,
                )
            )
        else:
            # Declared MORE than AIS. Usually fine, and occasionally a sign of
            # double counting — worth a note, not an alarm.
            result.findings.append(
                Finding(
                    category, Severity.LOW, ais_total, declared_amount,
                    message=(
                        f"You have declared ₹{declared_amount:,.0f} of "
                        f"{category.label}, which is ₹{abs(difference):,.0f} MORE "
                        f"than the AIS records."
                    ),
                    action=(
                        "No action needed — declaring more than the AIS shows is "
                        "not a problem. Worth a glance in case something was "
                        "counted twice."
                    ),
                )
            )

    # Declared categories with no AIS counterpart. Not a risk, but if the AIS
    # is genuinely missing something the department may still hold the data.
    for category, amount in sorted(normalised.items(), key=lambda kv: kv[0].value):
        if category.is_income and category not in ais.by_category() and amount > 0:
            result.findings.append(
                Finding(
                    category, Severity.LOW, Decimal(0), amount,
                    message=(
                        f"You have declared ₹{amount:,.0f} of {category.label} "
                        f"that does not appear in the AIS."
                    ),
                    action="No action needed. Declaring income the AIS missed is correct.",
                )
            )

    result.findings.sort(
        key=lambda f: [Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO].index(f.severity)
    )
    return result
