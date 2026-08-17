"""Deadline calendar — PLN-005.

The claims worth testing:

  * the ITR date follows s.44AB AUDIT LIABILITY, not the ITR form number
  * the 31 August category exists at all — it is new, permanent, and a tool
    carrying the old two-date model is a month wrong for every non-audit
    freelancer
  * a person is never shown a deadline they do not have; v1 fired the same
    reminders at everybody
  * losing a loss carry-forward outranks every other consequence
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.core.rules import load_ruleset
from backend.core.tax_engine.deadlines import (
    TaxpayerProfile as P,
)
from backend.core.tax_engine.deadlines import (
    Urgency,
    build_calendar,
    days_until_itr_u_closes,
    itr_due_date,
)

FY = "2026-27"
RS = load_ruleset(FY)
EARLY = date(2026, 6, 1)


def _cal(as_of: date = EARLY, **kw):
    return build_calendar(P(**kw), FY, as_of=as_of)


def _names(cal) -> str:
    return " | ".join(d.name for d in cal.deadlines)


# ══ the ITR date — audit liability, not form ════════════════════════════════

class TestTheItrDueDate:
    def test_no_business_income_is_the_thirty_first_of_july(self) -> None:
        assert itr_due_date(P(), RS)[0] == date(2027, 7, 31)

    def test_business_income_without_audit_is_the_thirty_first_of_august(self) -> None:
        """The date this module exists to get right. Created permanently by
        the Finance Act 2026 substituting Explanation 2 to s.139(1), effective
        AY 2026-27 — a statutory amendment, not an extension circular. A tool
        still on the old two-date model tells this person 31 July."""
        due, why = itr_due_date(P(has_business_income=True), RS)
        assert due == date(2027, 8, 31)
        assert "NOT liable to audit" in why

    def test_audit_liability_moves_it_back_to_october(self) -> None:
        assert itr_due_date(
            P(has_business_income=True, is_audit_liable=True), RS
        )[0] == date(2027, 10, 31)

    def test_a_company_is_always_october(self) -> None:
        assert itr_due_date(P(is_company=True), RS)[0] == date(2027, 10, 31)

    def test_transfer_pricing_beats_everything_else(self) -> None:
        """s.92E is checked first because it is the most specific."""
        assert itr_due_date(
            P(has_business_income=True, is_audit_liable=True,
              has_transfer_pricing=True), RS
        )[0] == date(2027, 11, 30)

    def test_the_same_profile_shape_can_have_two_different_dates(self) -> None:
        """The point of the whole section. Two people who would file the same
        form are a month apart because one is audit-liable."""
        a = itr_due_date(P(has_business_income=True), RS)[0]
        b = itr_due_date(P(has_business_income=True, is_audit_liable=True), RS)[0]
        assert a != b

    def test_the_reason_is_returned_with_the_date(self) -> None:
        """A date with no reason cannot be checked by the person it applies
        to."""
        for profile in (P(), P(has_business_income=True),
                        P(is_audit_liable=True), P(has_transfer_pricing=True)):
            assert itr_due_date(profile, RS)[1].strip()


# ══ nothing you do not owe ══════════════════════════════════════════════════

class TestOnlyWhatYouOwe:
    def test_a_salaried_filer_sees_no_advance_tax_instalments(self) -> None:
        """v1 fired quarterly advance-tax reminders at salaried employees with
        full TDS. Reminders that do not apply train people to ignore the ones
        that do."""
        assert "Advance tax" not in _names(_cal())

    def test_but_is_told_why_they_are_absent(self) -> None:
        """Silence could mean "you have none" or "we did not check"."""
        assert any("₹10,000 or more after TDS" in n for n in _cal().notes)

    def test_advance_tax_appears_when_it_is_owed(self) -> None:
        cal = _cal(owes_advance_tax=True)
        assert len([d for d in cal.deadlines if "Advance tax" in d.name]) == 4

    def test_the_instalment_labels_read_correctly(self) -> None:
        """Not a cosmetic test. `format_rate` already multiplies by 100, and
        multiplying again produced "Advance tax — 1500% cumulative" — which
        every other test in this file passed straight over, because none of
        them looked at the label."""
        cal = _cal(owes_advance_tax=True)
        labels = [d.name for d in cal.deadlines if "Advance tax" in d.name]
        assert labels == [
            "Advance tax — 15% cumulative",
            "Advance tax — 45% cumulative",
            "Advance tax — 75% cumulative",
            "Advance tax — 100% cumulative",
        ]

    def test_a_senior_without_business_income_gets_no_instalments(self) -> None:
        """s.207(2) exempts them, so listing four instalments would be wrong
        even though they owe tax."""
        cal = _cal(owes_advance_tax=True, age=68)
        assert "Advance tax" not in _names(cal)

    def test_but_a_senior_with_business_income_does(self) -> None:
        cal = _cal(owes_advance_tax=True, age=68, has_business_income=True)
        assert "Advance tax" in _names(cal)

    def test_tds_statements_only_for_a_deductor(self) -> None:
        assert "TDS/TCS" not in _names(_cal())
        assert "TDS/TCS" in _names(_cal(is_tds_deductor=True))

    def test_an_empty_profile_produces_a_short_calendar(self) -> None:
        """Three return deadlines, nothing invented."""
        assert len(_cal().deadlines) == 3


# ══ the consequence that actually costs money ═══════════════════════════════

class TestLossCarryForward:
    def test_it_raises_the_return_to_critical(self) -> None:
        assert _cal().deadlines[0].urgency is Urgency.HIGH
        assert _cal(has_loss_to_carry_forward=True).deadlines[0].urgency is (
            Urgency.CRITICAL
        )

    def test_the_note_says_a_revised_return_cannot_fix_it(self) -> None:
        """The part people get wrong: the condition attaches to the ORIGINAL
        filing, so revising later does not restore the loss."""
        note = next(
            n for n in _cal(has_loss_to_carry_forward=True).notes
            if "carry forward" in n
        )
        assert "cannot restore it" in note
        assert "original" in note

    def test_the_exceptions_are_named(self) -> None:
        note = next(
            n for n in _cal(has_loss_to_carry_forward=True).notes
            if "carry forward" in n
        )
        assert "House property loss" in note
        assert "unabsorbed depreciation" in note


# ══ TDS form renumbering ════════════════════════════════════════════════════

class TestTdsFormNumbers:
    def test_the_new_form_numbers_are_surfaced(self) -> None:
        """Every quarterly TDS/TCS form was renumbered from 1 April 2026 under
        the Income-tax Rules 2026. Filing on an old number gets the return
        rejected, so a reminder that says "file your 24Q" is actively
        harmful."""
        d = next(x for x in _cal(is_tds_deductor=True).deadlines
                 if "TDS/TCS" in x.name)
        assert "Form 138" in d.consequence
        assert "was 24Q" in d.consequence
        assert "Form 140" in d.consequence

    def test_the_dates_themselves_did_not_change(self) -> None:
        cal = _cal(is_tds_deductor=True)
        due = sorted(d.due_on for d in cal.deadlines if "TDS/TCS" in d.name)
        assert due == [
            date(2026, 7, 31), date(2026, 10, 31),
            date(2027, 1, 31), date(2027, 5, 31),
        ]

    def test_the_daily_late_fee_is_stated(self) -> None:
        d = next(x for x in _cal(is_tds_deductor=True).deadlines
                 if "TDS/TCS" in x.name)
        assert "₹200 per day" in d.consequence


# ══ presentation ════════════════════════════════════════════════════════════

class TestCalendarBehaviour:
    def test_deadlines_come_back_in_date_order(self) -> None:
        cal = _cal(owes_advance_tax=True, is_tds_deductor=True)
        dates = [d.due_on for d in cal.deadlines]
        assert dates == sorted(dates)

    def test_a_date_that_has_gone_is_marked_passed_not_critical(self) -> None:
        """Leaving an expired deadline red is how a calendar becomes noise."""
        cal = _cal(as_of=date(2027, 9, 1), has_loss_to_carry_forward=True)
        itr = next(d for d in cal.deadlines if d.name == "Income tax return")
        assert itr.days_from(cal.as_of) < 0
        assert itr.urgency is Urgency.PASSED

    def test_next_deadline_skips_the_ones_already_gone(self) -> None:
        cal = _cal(as_of=date(2027, 9, 1))
        assert cal.next_deadline().due_on >= cal.as_of

    def test_upcoming_is_bounded_by_its_window(self) -> None:
        cal = _cal(as_of=date(2027, 6, 1), owes_advance_tax=True)
        assert all(0 <= d.days_from(cal.as_of) <= 30 for d in cal.upcoming(30))

    def test_next_deadline_is_none_when_the_year_is_over(self) -> None:
        assert _cal(as_of=date(2030, 1, 1)).next_deadline() is None

    def test_serialises_with_days_remaining(self) -> None:
        d = _cal(as_of=date(2027, 7, 1)).to_dict()
        itr = next(x for x in d["deadlines"] if x["name"] == "Income tax return")
        assert itr["days_remaining"] == 30
        assert d["next"]["name"] == "Income tax return"


def test_the_revised_return_window_and_its_fee() -> None:
    """From AY 2026-27 the revised window runs three months past the belated
    one, with a s.234I fee if used after 31 December."""
    cal = build_calendar(P(), FY, as_of=EARLY)
    revised = next(d for d in cal.deadlines if d.name == "Revised return")
    assert revised.due_on == date(2028, 3, 31)
    assert "s.234I" in revised.consequence


def test_gst_absence_is_declared_rather_than_implied() -> None:
    """A GST-registered business must not read this calendar as complete."""
    cal = _cal(is_gst_registered=True)
    assert any("not in this calendar yet" in n for n in cal.notes)
    assert any("do not treat this calendar as complete" in n.lower()
               for n in cal.notes)


def test_the_itr_u_window_runs_from_the_end_of_the_assessment_year() -> None:
    """48 months from the END of the relevant AY, not from the due date —
    a distinction worth a year if you get it wrong.

    AY 2027-28 ends 31 March 2028; 48 months on is 31 March 2032. Asked on
    1 April 2027 that is 1,826 days, five calendar years, because the window
    starts a year after the financial year does.
    """
    days = days_until_itr_u_closes(FY, date(2027, 4, 1), RS)
    assert 1820 <= days <= 1830


@pytest.mark.parametrize("as_of", [date(2026, 4, 1), date(2027, 3, 31)])
def test_the_calendar_is_stable_across_the_financial_year(as_of) -> None:
    """Statutory dates are civil dates. They do not move with when you ask,
    and they do not move with a timezone."""
    a = build_calendar(P(has_business_income=True), FY, as_of=as_of)
    assert next(d for d in a.deadlines
                if d.name == "Income tax return").due_on == date(2027, 8, 31)
