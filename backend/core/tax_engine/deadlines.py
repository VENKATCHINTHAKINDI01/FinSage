"""Deadlines derived from what a person actually owes — PLN-005.

What this replaces
------------------
v1 had hardcoded global scheduler jobs firing the same reminders at every user
on the same days. A salaried employee with full TDS was told about quarterly
advance tax instalments they did not owe, and a freelancer was told 31 July
when their date is 31 August. Reminders that do not apply to you are worse than
none: they train you to ignore the ones that do.

The rule that decides the ITR date
----------------------------------
**Audit liability under s.44AB, not the ITR form number.** Two people on the
same form can have different deadlines, and sorting by form is how a filing
gets missed:

    no business or professional income          31 July
    business income, NOT audit-liable           31 August   ← new
    audit-liable, and all companies             31 October
    transfer pricing under s.92E                30 November

The 31 August date is new. The Finance Act 2026 substituted Explanation 2 to
s.139(1) and created it permanently from AY 2026-27 — a statutory amendment,
not a CBDT extension circular, so there is no annual notification to wait for.
A tool still carrying the old two-date model tells a non-audit freelancer
31 July, a month early.

Dates, not instants
-------------------
Everything here is a `date`, never a `datetime`. A statutory deadline is a
civil date in India: "31 July" does not move with the reader's timezone.
Carrying these as timezone.utc instants is how a reminder fires on the 30th for a user
in Mumbai, and how an offset constant ends up as a float in a module that is
forbidden floats. The scheduling layer converts to IST instants at the boundary
where it must; the calendar itself stays in civil dates.

Why the loss carry-forward warning gets its own treatment
----------------------------------------------------------
The late-filing fee is ₹1,000 or ₹5,000 and everyone knows about it. Losing the
carry-forward of a business or capital loss is unbounded, is discovered a year
late, and cannot be fixed by revising — the condition attaches to the ORIGINAL
filing. For anyone sitting on a real loss it is worth more than every other
consequence combined, so it is raised to CRITICAL rather than left in a list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any

from backend.core.provenance.money import format_rate
from backend.core.rules.aliases import cite
from backend.core.rules.loader import TaxRuleset, load_ruleset


class Urgency(str, Enum):
    CRITICAL = "critical"     # missing it forfeits something unrecoverable
    HIGH = "high"             # money cost that grows
    NORMAL = "normal"
    PASSED = "passed"


@dataclass(slots=True)
class TaxpayerProfile:
    """What a person's obligations actually are.

    Every flag defaults to the *no obligation* value. A profile that has not
    been filled in produces a short calendar rather than a long wrong one.
    """

    has_business_income: bool = False
    is_audit_liable: bool = False
    has_transfer_pricing: bool = False
    is_company: bool = False

    owes_advance_tax: bool = False
    is_tds_deductor: bool = False
    is_gst_registered: bool = False
    gst_quarterly_qrmp: bool = False

    has_loss_to_carry_forward: bool = False
    age: int = 0


@dataclass(frozen=True, slots=True)
class Deadline:
    name: str
    due_on: date
    urgency: Urgency
    why: str
    consequence: str = ""
    legacy_section: str | None = None

    def days_from(self, today: date) -> int:
        return (self.due_on - today).days

    def to_dict(self, today: date) -> dict[str, Any]:
        return {
            "name": self.name,
            "due_on": self.due_on.isoformat(),
            "days_remaining": self.days_from(today),
            "urgency": self.urgency.value,
            "why": self.why,
            "consequence": self.consequence,
            "section": self.legacy_section,
        }


@dataclass(slots=True)
class Calendar:
    fy: str
    as_of: date
    deadlines: list[Deadline]
    notes: list[str] = field(default_factory=list)

    def upcoming(self, within_days: int = 90) -> list[Deadline]:
        return [
            d for d in self.deadlines
            if 0 <= d.days_from(self.as_of) <= within_days
        ]

    def next_deadline(self) -> Deadline | None:
        future = [d for d in self.deadlines if d.days_from(self.as_of) >= 0]
        return min(future, key=lambda d: d.due_on) if future else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "fy": self.fy,
            "as_of": self.as_of.isoformat(),
            "deadlines": [d.to_dict(self.as_of) for d in self.deadlines],
            "next": (
                self.next_deadline().to_dict(self.as_of)
                if self.next_deadline() else None
            ),
            "notes": self.notes,
        }


def _d(value: Any) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def itr_due_date(profile: TaxpayerProfile, rs: TaxRuleset) -> tuple[date, str]:
    """The one that is easy to get wrong, and the reason for it.

    Ordered most-specific first. s.92E beats audit liability, audit liability
    beats the business-income category, and the plain 31 July date is the
    residual — which is exactly how the Department's own calendar frames it
    ("an assessee, other than the following").
    """
    dl = rs.deadlines
    if profile.has_transfer_pricing:
        return _d(dl["itr_transfer_pricing"]), (
            "you must furnish a transfer pricing report under s.92E"
        )
    if profile.is_audit_liable or profile.is_company:
        return _d(dl["itr_audit"]), (
            "your accounts are liable to audit under s.44AB"
            if profile.is_audit_liable else "you are filing for a company"
        )
    if profile.has_business_income:
        return _d(dl["itr_business_non_audit"]), (
            "you have income from business or profession and your accounts are "
            "NOT liable to audit — the Finance Act 2026 gave this group a "
            "permanent extra month from AY 2026-27"
        )
    return _d(dl["itr_non_audit"]), (
        "you have no income from business or profession"
    )


def build_calendar(
    profile: TaxpayerProfile,
    fy: str,
    *,
    as_of: date,
    ruleset: TaxRuleset | None = None,
) -> Calendar:
    """Only the deadlines this person actually has."""
    rs = ruleset or load_ruleset(fy)
    dl = rs.deadlines
    out: list[Deadline] = []
    notes: list[str] = []

    # ── the return ──────────────────────────────────────────────────────────
    itr_date, why = itr_due_date(profile, rs)
    fee = dl["late_filing"]
    out.append(Deadline(
        name="Income tax return",
        due_on=itr_date,
        urgency=Urgency.CRITICAL if profile.has_loss_to_carry_forward else Urgency.HIGH,
        why=why,
        consequence=(
            f"Late filing costs a s.234F fee of "
            f"₹{fee['fee_234f_upto_5L']:,} or ₹{fee['fee_234f_above_5L']:,} "
            f"depending on income, plus 1% a month under s.234A on unpaid tax."
        ),
        legacy_section="139",
    ))

    if profile.has_loss_to_carry_forward:
        notes.append(
            f"You have a loss to carry forward, so {itr_date.isoformat()} is a "
            f"hard wall rather than a soft target. Filing even one day late "
            f"forfeits the carry-forward permanently, and a revised return "
            f"cannot restore it — the condition attaches to the original "
            f"filing. House property loss and unabsorbed depreciation are the "
            f"only exceptions."
        )

    out.append(Deadline(
        name="Belated return",
        due_on=_d(dl["belated"]),
        urgency=Urgency.NORMAL,
        why="the last date to file at all under s.139(4)",
        consequence="After this only an updated return under s.139(8A) remains.",
        legacy_section="139",
    ))
    out.append(Deadline(
        name="Revised return",
        due_on=_d(dl["revised"]),
        urgency=Urgency.NORMAL,
        why="correcting a return already filed, under s.139(5)",
        consequence=(
            f"From AY 2026-27 this runs to the end of the assessment year, "
            f"three months past the belated date — but a s.234I fee of "
            f"₹{dl['revised_late_fee']['upto_5L_total_income']:,} or "
            f"₹{dl['revised_late_fee']['above_5L_total_income']:,} applies "
            f"after {dl['revised_late_fee_after']}."
        ),
        legacy_section="139",
    ))

    # ── advance tax ─────────────────────────────────────────────────────────
    if profile.owes_advance_tax:
        _add_advance_tax(out, rs, profile)
    else:
        notes.append(
            "No advance tax instalments are listed because your profile does "
            "not show a liability of ₹10,000 or more after TDS. If that "
            "changes during the year, the instalments restart from the next "
            "quarter."
        )

    # ── TDS, if they deduct ─────────────────────────────────────────────────
    if profile.is_tds_deductor:
        _add_tds(out, rs)

    if profile.is_gst_registered:
        notes.append(
            "GST return dates are not in this calendar yet. GSTR-1 and GSTR-3B "
            "run on a separate monthly or QRMP cycle set by the GST Council, "
            "not by the Income-tax Act, and are tracked in a later release. "
            "Do not treat this calendar as complete for a GST-registered "
            "business."
        )

    out.sort(key=lambda d: d.due_on)
    out = [_repriced(d, as_of) for d in out]
    return Calendar(fy=rs.fy, as_of=as_of, deadlines=out, notes=notes)


def _repriced(d: Deadline, today: date) -> Deadline:
    """A date that has gone is not 'critical', it is gone. Leaving it red is
    how a calendar becomes noise."""
    if d.days_from(today) < 0:
        return Deadline(
            d.name, d.due_on, Urgency.PASSED, d.why, d.consequence,
            d.legacy_section,
        )
    return d


def _add_advance_tax(
    out: list[Deadline], rs: TaxRuleset, profile: TaxpayerProfile
) -> None:
    from backend.core.tax_engine.advance_tax import instalment_date

    cfg = rs.advance_tax
    min_age = int(cfg.get("senior_citizen_min_age", 60))
    if (
        cfg.get("senior_citizen_exempt_without_business_income")
        and profile.age >= min_age
        and not profile.has_business_income
    ):
        return

    for row in cfg["instalments"]:
        # Decimal, not float, even for a label. The purity guard caught this
        # as a `float()` call in core and it was right to: a rule that only
        # applies to figures a user might rely on is a rule with an exception,
        # and exceptions are how floats get back into money paths.
        pct = format_rate(Decimal(str(row["cumulative_percent"])))
        out.append(Deadline(
            name=f"Advance tax — {pct}% cumulative",
            due_on=instalment_date(rs.fy, row["due"]),
            urgency=Urgency.HIGH,
            why="you owe ₹10,000 or more in tax after TDS (s.208)",
            consequence=(
                "A shortfall attracts 1% a month under s.234C, and paying "
                "under 90% of the assessed tax adds s.234B on top."
            ),
            legacy_section="211",
        ))


def _add_tds(out: list[Deadline], rs: TaxRuleset) -> None:
    cfg = rs.deadlines["tds_returns"]
    forms = cfg["forms"]
    for row in cfg["quarters"]:
        out.append(Deadline(
            name=f"TDS/TCS statement — {row['quarter']} ({row['period']})",
            due_on=_d(row["due"]),
            urgency=Urgency.HIGH,
            why="you deduct or collect tax at source",
            consequence=(
                f"₹{cfg['late_fee_per_day']} per day of delay, capped at the "
                f"tax in the return. Use the NEW form numbers: salary is now "
                f"Form {forms['salary']['new']} (was "
                f"{forms['salary']['old']}), resident non-salary is Form "
                f"{forms['resident_non_salary']['new']} (was "
                f"{forms['resident_non_salary']['old']}). An old form number "
                f"gets the return rejected."
            ),
            legacy_section="200(3)",
        ))


def citations_for(profile: TaxpayerProfile, fy: str) -> list[Any]:
    refs = [cite("139", fy)]
    if profile.owes_advance_tax:
        refs.extend([cite("208", fy), cite("211", fy)])
    if profile.is_tds_deductor:
        refs.append(cite("200", fy))
    return refs


def days_until_itr_u_closes(fy: str, as_of: date, rs: TaxRuleset) -> int:
    """The updated-return window, which is measured from the END of the
    assessment year rather than from the due date — a distinction that costs
    people a year if they get it wrong."""
    months = int(rs.deadlines["updated_return_itr_u_months"])
    ay_end = date(int(rs.assessment_year.split("-")[0]) + 1, 3, 31)
    closes = ay_end + timedelta(days=int(months * 30.4375))
    return (closes - as_of).days


__all__ = [
    "Calendar",
    "Deadline",
    "TaxpayerProfile",
    "Urgency",
    "build_calendar",
    "citations_for",
    "days_until_itr_u_closes",
    "itr_due_date",
]
