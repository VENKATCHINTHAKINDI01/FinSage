"""Advance tax, and the interest for getting it wrong — PLN-002.

Two questions, opposite directions in time:

    plan_advance_tax()   what should I pay, and by when?
    compute_interest()   I already paid what I paid — what do I owe now?

Both come off one schedule in the rule pack, so a plan the product issued in
June cannot disagree with the interest it charges in March.

The three rules a calculator usually gets wrong
-----------------------------------------------
**The tolerance is not the target.** s.234C charges nothing if you paid 12% by
15 June, even though the instalment is 15%. But once it does charge, it charges
on the shortfall from 15%, not from 12%. Two different percentages doing two
different jobs in one sub-clause. Treating them as one number is wrong in one
direction or the other for everybody who lands between them.

**Rule 119A rounds against you, twice.** The amount interest runs on is floored
to a multiple of ₹100, and any part of a month counts as a whole month. A
₹8,489 shortfall over three months and ten days is interest on ₹8,400 for four
months.

**Unforecastable income is excused.** Nobody can predict a capital gain in
February at the June instalment date, and the Act does not ask them to. Tax on
gains, lottery winnings, dividends and first-year business income drops out of
the deferment calculation for every instalment falling before the income arose,
provided it is paid in the instalments that remain. Without this the product
tells someone who sold shares in February that they owe interest back to June —
confidently, and wrongly.

s.234B and s.234C both apply
-----------------------------
They are not alternatives and one is not a subset of the other. 234C is about
*when* you paid within the year; 234B is about whether you got to 90% of the
assessed tax at all, and runs from 1 April of the assessment year until the tax
is paid. A taxpayer can owe both on the same default.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from backend.core.provenance.citation import Citation
from backend.core.provenance.money import ZERO, Money, pct_of
from backend.core.provenance.trace import Trace
from backend.core.rules.aliases import cite
from backend.core.rules.loader import TaxRuleset, load_ruleset


def _fy_start_year(fy: str) -> int:
    """'2026-27' → 2026. The instalment months belong to the FY, not the AY."""
    return int(fy.split("-")[0])


def instalment_date(fy: str, due: str) -> date:
    """Resolve 'MM-DD' against the right calendar year.

    June, September and December fall in the first calendar year of the FY;
    March falls in the second. Hardcoding either is how a planner ends up
    telling someone their March instalment was due twelve months early.
    """
    month, day = (int(part) for part in due.split("-"))
    year = _fy_start_year(fy) + (1 if month <= 3 else 0)
    return date(year, month, day)


def round_119a(amount: Money) -> Money:
    """Rule 119A(c): floor to a multiple of ₹100.

    "Rounded off to the nearest multiple of one hundred rupees and any fraction
    of one hundred rupees shall be ignored" — the second half governs, so a
    ₹8,489 shortfall attracts interest on ₹8,400, not ₹8,500.
    """
    hundreds = int(amount.amount // 100)
    return Money(hundreds * 100)


def months_119a(fraction: Decimal | int) -> int:
    """Rule 119A(b): any part of a month is a full month."""
    whole = int(fraction)
    return whole + 1 if Decimal(fraction) > whole else whole


# ── the schedule ────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class Instalment:
    """One row of the schedule, and what it cost."""

    due_on: date
    cumulative_percent: Decimal
    tolerance_percent: Decimal
    interest_months: int

    required: Money = ZERO          # cumulative_percent of the liability
    tolerated: Money = ZERO         # tolerance_percent — the trigger, not the base
    paid_by_due_date: Money = ZERO
    shortfall: Money = ZERO         # from `required`, which is what interest runs on
    interest: Money = ZERO
    excused: Money = ZERO           # tax on income that had not arisen yet

    @property
    def is_short(self) -> bool:
        return self.interest > ZERO

    def to_dict(self) -> dict[str, Any]:
        return {
            "due_on": self.due_on.isoformat(),
            "cumulative_percent": f"{self.cumulative_percent * 100:.0f}%",
            "required": self.required.to_json(),
            "paid_by_due_date": self.paid_by_due_date.to_json(),
            "shortfall": self.shortfall.to_json(),
            "excused": self.excused.to_json(),
            "interest": self.interest.to_json(),
            "interest_months": self.interest_months,
        }


@dataclass(slots=True)
class AdvanceTaxPlan:
    fy: str
    total_tax: Money
    taxes_deducted: Money
    liability: Money                # assessed tax: total tax less TDS/TCS
    is_liable: bool
    exemption_reason: str
    schedule: list[Instalment]
    interest_234c: Money
    interest_234b: Money
    total_interest: Money
    trace: Trace
    notes: list[str] = field(default_factory=list)

    @property
    def total_payable(self) -> Money:
        return self.liability + self.total_interest

    def citations(self) -> list[Citation]:
        refs = [cite("208", self.fy), cite("211", self.fy)]
        if self.interest_234c > ZERO:
            refs.append(cite("234C", self.fy))
        if self.interest_234b > ZERO:
            refs.append(cite("234B", self.fy))
        return refs

    def summary(self) -> str:
        if not self.is_liable:
            return f"You are not required to pay advance tax. {self.exemption_reason}"
        if self.total_interest <= ZERO:
            return (
                f"Advance tax of {self.liability} is due across "
                f"{len(self.schedule)} instalment(s). No interest is payable on "
                f"what you have paid so far."
            )
        parts = []
        if self.interest_234c > ZERO:
            parts.append(f"{self.interest_234c} under s.234C for late instalments")
        if self.interest_234b > ZERO:
            parts.append(f"{self.interest_234b} under s.234B for paying under 90%")
        return f"Interest of {self.total_interest} is payable: " + " and ".join(parts) + "."

    def to_dict(self) -> dict[str, Any]:
        return {
            "fy": self.fy,
            "liability": self.liability.to_json(),
            "is_liable": self.is_liable,
            "exemption_reason": self.exemption_reason,
            "schedule": [i.to_dict() for i in self.schedule],
            "interest_234c": self.interest_234c.to_json(),
            "interest_234b": self.interest_234b.to_json(),
            "total_interest": self.total_interest.to_json(),
            "total_payable": self.total_payable.to_json(),
            "summary": self.summary(),
            "notes": self.notes,
            "worksheet": self.trace.render(),
            "citations": [c.to_dict() for c in self.citations()],
        }


# ── liability ───────────────────────────────────────────────────────────────

def _exemption(
    liability: Money,
    rs: TaxRuleset,
    age: int,
    has_business_income: bool,
) -> str:
    """Why this taxpayer owes no advance tax, or '' if they do."""
    cfg = rs.advance_tax
    threshold = Money(cfg["threshold"])

    if liability < threshold:
        return (
            f"Your liability after TDS is {liability}, below the {threshold} "
            f"threshold in s.208."
        )

    min_age = int(cfg.get("senior_citizen_min_age", 60))
    if (
        cfg.get("senior_citizen_exempt_without_business_income")
        and age >= min_age
        and not has_business_income
    ):
        return (
            f"A resident aged {min_age} or over with no business or "
            f"professional income is exempt from advance tax under s.207(2). "
            f"The tax is still due, by 31 July as self-assessment tax."
        )
    return ""


def _schedule_for(rs: TaxRuleset, is_presumptive: bool) -> list[dict[str, Any]]:
    """Four instalments, or one.

    A 44AD/44ADA taxpayer pays the lot by 15 March. Running them through the
    four-instalment schedule would invent three defaults that do not exist.
    """
    rows = [dict(r) for r in rs.advance_tax["instalments"]]
    if not is_presumptive:
        return rows
    final = dict(rows[-1])
    final["cumulative_percent"] = "1.00"
    final["tolerance_percent"] = "1.00"
    return [final]


# ── the calculation ─────────────────────────────────────────────────────────

def plan_advance_tax(
    total_tax: Money | int,
    fy: str,
    *,
    taxes_deducted: Money | int = 0,
    payments: dict[date, Money] | None = None,
    age: int = 0,
    has_business_income: bool = False,
    is_presumptive: bool = False,
    excused_tax_by_date: dict[date, Money] | None = None,
    assessed_on: date | None = None,
    ruleset: TaxRuleset | None = None,
) -> AdvanceTaxPlan:
    """Build the schedule and price every shortfall.

    `payments` is what was actually paid and when. Pass nothing and you get a
    forward-looking plan with the full schedule outstanding — which is the same
    calculation, with every instalment short.

    `excused_tax_by_date` is tax on income that had not arisen by a given date:
    capital gains, lottery winnings, dividends, first-year business income.
    Keyed by the date the income arose, so instalments falling before it drop
    that tax out of the shortfall and later ones do not.
    """
    rs = ruleset or load_ruleset(fy)
    total_tax = Money(total_tax)
    taxes_deducted = Money(taxes_deducted)
    payments = dict(payments or {})
    excused_tax_by_date = dict(excused_tax_by_date or {})

    trace = Trace(f"Advance tax — FY {rs.fy}")
    trace.literal("Total tax liability", total_tax)
    notes: list[str] = []

    liability = (total_tax - taxes_deducted).clamp_non_negative()
    if taxes_deducted > ZERO:
        trace.subtract("Less: TDS and TCS", total_tax, taxes_deducted)

    reason = _exemption(liability, rs, age, has_business_income)
    if reason:
        return AdvanceTaxPlan(
            fy=rs.fy, total_tax=total_tax, taxes_deducted=taxes_deducted,
            liability=liability, is_liable=False, exemption_reason=reason,
            schedule=[], interest_234c=ZERO, interest_234b=ZERO,
            total_interest=ZERO, trace=trace, notes=[reason],
        )

    if is_presumptive:
        notes.append(
            "As a presumptive taxpayer under s.44AD or s.44ADA you pay the "
            "whole amount by 15 March in one instalment, not in four."
        )

    rate = Decimal(str(rs.advance_tax["interest"]["234C"]["rate_monthly"]))
    schedule: list[Instalment] = []
    interest_234c = ZERO

    for row in _schedule_for(rs, is_presumptive):
        due = instalment_date(rs.fy, row["due"])
        cumulative = Decimal(str(row["cumulative_percent"]))
        tolerance = Decimal(str(row.get("tolerance_percent", row["cumulative_percent"])))
        months = int(row.get("months", 3))

        # Tax on income that had not yet arisen is not deferred by not paying it.
        excused = ZERO
        for arose_on, amount in excused_tax_by_date.items():
            if arose_on > due:
                excused = excused + amount

        chargeable = (liability - excused).clamp_non_negative()
        required = pct_of(chargeable, cumulative)
        tolerated = pct_of(chargeable, tolerance)
        paid = ZERO
        for when, amount in payments.items():
            if when <= due:
                paid = paid + amount

        shortfall = ZERO
        interest = ZERO
        if paid < tolerated:
            # Triggered by the tolerance, but charged on the shortfall from the
            # full instalment. Two percentages, two jobs.
            shortfall = (required - paid).clamp_non_negative()
            interest = pct_of(round_119a(shortfall), rate * months)

        interest_234c = interest_234c + interest
        schedule.append(
            Instalment(
                due_on=due, cumulative_percent=cumulative,
                tolerance_percent=tolerance, interest_months=months,
                required=required, tolerated=tolerated, paid_by_due_date=paid,
                shortfall=shortfall, interest=interest, excused=excused,
            )
        )

    if interest_234c > ZERO:
        trace.sum_of(
            "Interest u/s 234C — deferment of instalments",
            *[i.interest for i in schedule if i.interest > ZERO],
        )

    interest_234b = _compute_234b(
        liability, payments, rs, trace, assessed_on, notes
    )

    total_interest = interest_234c + interest_234b
    if excused_tax_by_date:
        notes.append(
            "Tax on capital gains, lottery winnings, dividends and first-year "
            "business income is excluded from the instalments falling before "
            "that income arose, provided it is paid in the instalments that "
            "remain."
        )

    return AdvanceTaxPlan(
        fy=rs.fy, total_tax=total_tax, taxes_deducted=taxes_deducted,
        liability=liability, is_liable=True, exemption_reason="",
        schedule=schedule, interest_234c=interest_234c,
        interest_234b=interest_234b, total_interest=total_interest,
        trace=trace, notes=notes,
    )


@dataclass(slots=True)
class RefundInterest:
    refund: Money
    months: int
    rate_monthly: Decimal
    interest: Money
    trace: Trace
    denied_by_proviso: bool = False
    caveats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "refund": self.refund.to_json(),
            "months": self.months,
            "interest": self.interest.to_json(),
            "total_receivable": (self.refund + self.interest).to_json(),
            "denied_by_proviso": self.denied_by_proviso,
            "caveats": self.caveats,
            "worksheet": self.trace.render(),
        }


def refund_interest(
    refund: Money | int,
    fy: str,
    *,
    tax_determined: Money | int | None = None,
    from_self_assessment_tax: bool = False,
    granted_on: date | None = None,
    ruleset: TaxRuleset | None = None,
) -> RefundInterest:
    """Interest the department owes *you* on a refund — s.244A.

    Half a percent per month, from 1 April of the assessment year until the
    refund is granted. v1 used "1% per annum simplified", understating this by
    a factor of six: on a ₹50,000 refund granted nine months late that is
    ₹2,250 owed against ₹375 quoted.

    The 10% proviso
    ---------------
    No interest is payable where the refund is less than 10% of the tax
    determined under s.143(1) or on regular assessment. `tax_determined` is
    what the threshold is measured against; omit it and the proviso cannot be
    applied, so the figure is returned with a caveat rather than a silent
    assumption that it does not bite.

    The proviso is written against clauses (a) and (aa), but appellate
    authority has held the embargo does not reach refunds of self-assessment
    tax. `from_self_assessment_tax` follows that line and says so in a caveat,
    because a divergence between the bare text and the case law is exactly the
    thing a user needs told rather than decided for them.
    """
    rs = ruleset or load_ruleset(fy)
    refund = Money(refund)
    cfg = rs.advance_tax["interest"]["244A"]
    rate = Decimal(str(cfg["rate_monthly"]))

    start = date(_fy_start_year(rs.fy) + 1, 4, 1)
    until = max(granted_on or start, start)
    months = (until.year - start.year) * 12 + (until.month - start.month) + 1

    trace = Trace(f"Interest on refund — FY {rs.fy}")
    trace.literal("Refund due", refund)
    caveats: list[str] = []

    threshold_pct = Decimal(str(cfg.get("min_refund_percent_of_tax", "0")))
    denied = False

    if tax_determined is None:
        caveats.append(
            "No assessed tax was supplied, so the s.244A proviso could not be "
            "checked. If this refund is under 10% of the tax determined, no "
            "interest is payable at all and this figure is an upper bound."
        )
    elif threshold_pct > 0:
        floor = pct_of(Money(tax_determined), threshold_pct)
        if refund < floor:
            if from_self_assessment_tax and not cfg.get(
                "threshold_applies_to_self_assessment_tax", False
            ):
                caveats.append(
                    f"This refund of {refund} is under the {floor} proviso "
                    f"threshold, so on the bare text of s.244A no interest "
                    f"would be payable. Interest is shown here because "
                    f"appellate authority holds the embargo does not apply to "
                    f"refunds of self-assessment tax. Expect the department to "
                    f"take the other view."
                )
            else:
                denied = True
                trace.literal(
                    "Interest u/s 244A", ZERO,
                    citation=cite("244A", rs.fy),
                    note=(
                        f"refund of {refund} is under 10% of the tax determined "
                        f"({floor}), so the proviso denies interest"
                    ),
                )
                caveats.append(
                    f"No interest is payable: the proviso to s.244A denies it "
                    f"where the refund is under 10% of the tax determined, and "
                    f"{refund} is below that {floor} floor."
                )
                return RefundInterest(
                    refund=refund, months=months, rate_monthly=rate,
                    interest=ZERO, trace=trace, denied_by_proviso=True,
                    caveats=caveats,
                )

    base = round_119a(refund)
    interest = pct_of(base, rate * months)
    trace.multiply(
        f"Interest u/s 244A — {months} month(s) at 0.5%",
        base,
        rate * months,
        citation=cite("244A", rs.fy),
        note=f"from 1 April {start.year} to {until.isoformat()}",
    )

    return RefundInterest(
        refund=refund, months=months, rate_monthly=rate, interest=interest,
        trace=trace, denied_by_proviso=denied, caveats=caveats,
    )


def _compute_234b(
    liability: Money,
    payments: dict[date, Money],
    rs: TaxRuleset,
    trace: Trace,
    assessed_on: date | None,
    notes: list[str],
) -> Money:
    """Interest for paying less than 90% of the assessed tax.

    Runs from 1 April of the assessment year — not from any instalment date —
    until the tax is paid, on the whole unpaid balance. This is separate from
    and additional to s.234C.
    """
    cfg = rs.advance_tax["interest"]["234B"]
    trigger = Decimal(str(cfg["trigger_percent"]))
    rate = Decimal(str(cfg["rate_monthly"]))

    paid = ZERO
    for amount in payments.values():
        paid = paid + amount

    if paid >= pct_of(liability, trigger):
        return ZERO

    # Interest runs "from the 1st day of April" of the assessment year, so
    # April is month one — not month zero. An assessment determined in July is
    # four months (April, May, June, July), not three.
    start = date(_fy_start_year(rs.fy) + 1, 4, 1)
    until = max(assessed_on or start, start)
    months = (until.year - start.year) * 12 + (until.month - start.month) + 1

    unpaid = (liability - paid).clamp_non_negative()
    interest = pct_of(round_119a(unpaid), rate * months)

    trace.multiply(
        f"Interest u/s 234B — {months} month(s) at 1% on {round_119a(unpaid)}",
        round_119a(unpaid),
        rate * months,
        note=f"advance tax paid was under {trigger * 100:.0f}% of the assessed tax",
    )
    notes.append(
        f"You paid {paid} against an assessed tax of {liability}, below the "
        f"90% threshold in s.234B. Interest runs from 1 April "
        f"{start.year} until the balance is paid — it keeps accruing, so "
        f"paying sooner costs less."
    )
    return interest
