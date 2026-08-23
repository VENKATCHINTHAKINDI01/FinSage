"""Advance tax and ss.234B/234C interest — PLN-002.

Every expected figure here is arithmetic anyone can check in their head or on
paper: a percentage of a percentage. That is deliberate. Interest provisions
are where a plausible-looking wrong answer survives longest, because nobody
recomputes them.
"""

from __future__ import annotations

import pathlib
from datetime import date
from decimal import Decimal

import pytest

from backend.core.provenance.money import ZERO, Money, pct_of, rupees
from backend.core.tax_engine.advance_tax import (
    instalment_date,
    months_119a,
    plan_advance_tax,
    refund_interest,
    round_119a,
)

FY = "2026-27"
JUN, SEP, DEC, MAR = (
    date(2026, 6, 15), date(2026, 9, 15), date(2026, 12, 15), date(2027, 3, 15),
)


def _plan(total_tax: int = 100_000, **kw):
    kw.setdefault("has_business_income", True)   # keeps the senior test honest
    return plan_advance_tax(total_tax, FY, **kw)


# ══ Rule 119A ═══════════════════════════════════════════════════════════════

class TestRule119A:
    @pytest.mark.parametrize("amount,expected", [
        (8_489, 8_400),      # the worked example in the rule commentary
        (8_400, 8_400),
        (8_499, 8_400),
        (99, 0),
        (100, 100),
        (0, 0),
    ])
    def test_the_base_is_floored_to_a_hundred_not_rounded(self, amount, expected):
        """119A(c): "any fraction of one hundred rupees shall be ignored". The
        second half of the sentence governs — ₹8,489 becomes ₹8,400, not
        ₹8,500."""
        assert round_119a(rupees(amount)) == rupees(expected)

    @pytest.mark.parametrize("fraction,expected", [(3, 3), (3.1, 4), (0.1, 1), (0, 0)])
    def test_any_part_of_a_month_is_a_whole_month(self, fraction, expected):
        """119A(b). Pro-rating by days would understate every charge."""
        assert months_119a(Decimal(str(fraction))) == expected


def test_march_falls_in_the_second_calendar_year_of_the_fy() -> None:
    """June/September/December are 2026; March is 2027. Hardcoding either is
    how a planner announces that the March instalment was due last year."""
    assert instalment_date(FY, "06-15") == date(2026, 6, 15)
    assert instalment_date(FY, "03-15") == date(2027, 3, 15)


# ══ the schedule ════════════════════════════════════════════════════════════

class TestScheduleWithNothingPaid:
    """₹1,00,000 liability, nothing paid all year. Each figure is one
    multiplication:

        15,000 × 3% =   450
        45,000 × 3% = 1,350
        75,000 × 3% = 2,250
       1,00,000 × 1% = 1,000
                       -----
                       5,050
    """

    def test_four_instalments_at_the_statutory_percentages(self) -> None:
        s = _plan().schedule
        assert [i.due_on for i in s] == [JUN, SEP, DEC, MAR]
        assert [i.required for i in s] == [
            rupees(15_000), rupees(45_000), rupees(75_000), rupees(100_000)
        ]

    def test_each_instalments_interest(self) -> None:
        assert [i.interest for i in _plan().schedule] == [
            rupees(450), rupees(1_350), rupees(2_250), rupees(1_000)
        ]

    def test_the_march_instalment_runs_for_one_month_not_three(self) -> None:
        """There is no later instalment for it to be deferred against."""
        s = _plan().schedule
        assert s[3].interest_months == 1
        assert s[0].interest_months == 3

    def test_the_total(self) -> None:
        assert _plan().interest_234c == rupees(5_050)


# ══ the tolerance — the rule most calculators get wrong ═════════════════════

class TestTolerance:
    """s.234C(1)(a) uses two different percentages for two different jobs: 12%
    decides *whether* interest is charged, 15% decides *what it is charged on*.
    Collapsing them into one number is wrong in one direction or the other for
    everyone who lands between them."""

    def test_paying_exactly_twelve_percent_costs_nothing(self) -> None:
        p = _plan(payments={JUN: rupees(12_000)})
        assert p.schedule[0].interest == ZERO

    def test_a_rupee_under_twelve_percent_is_charged_on_the_gap_to_fifteen(self) -> None:
        """Not the gap to 12%. Paid ₹11,900, so the base is 15,000 − 11,900 =
        ₹3,100, floored to ₹3,100, at 3% = ₹93. Charging on the gap to 12%
        would give ₹3."""
        p = _plan(payments={JUN: rupees(11_900)})
        assert p.schedule[0].shortfall == rupees(3_100)
        assert p.schedule[0].interest == rupees(93)

    def test_thirty_six_percent_clears_the_september_instalment(self) -> None:
        p = _plan(payments={JUN: rupees(15_000), SEP: rupees(21_000)})
        assert p.schedule[1].paid_by_due_date == rupees(36_000)
        assert p.schedule[1].interest == ZERO

    def test_the_later_instalments_have_no_tolerance(self) -> None:
        """December and March are charged from the first rupee short — the
        concession exists only for the first two."""
        s = _plan().schedule
        assert s[2].tolerated == s[2].required
        assert s[3].tolerated == s[3].required

    def test_paying_on_time_all_year_costs_nothing_at_all(self) -> None:
        p = _plan(payments={
            JUN: rupees(15_000), SEP: rupees(30_000),
            DEC: rupees(30_000), MAR: rupees(25_000),
        })
        assert p.interest_234c == ZERO
        assert p.interest_234b == ZERO
        assert "No interest is payable" in p.summary()


def test_payments_accumulate_across_instalments() -> None:
    """The test is cumulative-to-date, not per-instalment. Overpaying in June
    must cover September."""
    p = _plan(payments={JUN: rupees(45_000)})
    assert p.schedule[0].interest == ZERO
    assert p.schedule[1].paid_by_due_date == rupees(45_000)
    assert p.schedule[1].interest == ZERO


# ══ who does not have to pay ════════════════════════════════════════════════

class TestExemptions:
    def test_under_the_ten_thousand_threshold(self) -> None:
        p = plan_advance_tax(9_999, FY, has_business_income=True)
        assert not p.is_liable
        assert "s.208" in p.exemption_reason

    def test_tds_can_take_you_under_the_threshold(self) -> None:
        """The threshold applies to what is left after TDS, not to the gross
        liability. A salaried taxpayer with full TDS owes no advance tax on a
        ₹5,00,000 bill."""
        p = plan_advance_tax(500_000, FY, taxes_deducted=495_000,
                             has_business_income=True)
        assert p.liability == rupees(5_000)
        assert not p.is_liable

    def test_a_senior_citizen_without_business_income_is_exempt(self) -> None:
        p = plan_advance_tax(100_000, FY, age=62, has_business_income=False)
        assert not p.is_liable
        assert "s.207(2)" in p.exemption_reason

    def test_but_a_senior_with_business_income_is_not(self) -> None:
        p = plan_advance_tax(100_000, FY, age=62, has_business_income=True)
        assert p.is_liable

    def test_and_neither_is_someone_under_sixty(self) -> None:
        p = plan_advance_tax(100_000, FY, age=59, has_business_income=False)
        assert p.is_liable

    def test_the_exempt_senior_is_told_the_tax_is_still_due(self) -> None:
        """Exempt from *advance* tax is not exempt from tax. Someone who reads
        it the other way gets a s.234A charge instead."""
        p = plan_advance_tax(100_000, FY, age=70, has_business_income=False)
        assert "still due" in p.exemption_reason


# ══ presumptive taxpayers ═══════════════════════════════════════════════════

class TestPresumptive:
    def test_one_instalment_not_four(self) -> None:
        """s.211 proviso. Running a 44AD taxpayer through the four-instalment
        schedule invents three defaults that do not exist."""
        p = _plan(is_presumptive=True)
        assert len(p.schedule) == 1
        assert p.schedule[0].due_on == MAR
        assert p.schedule[0].required == rupees(100_000)

    def test_the_whole_liability_by_fifteen_march_costs_nothing(self) -> None:
        p = _plan(is_presumptive=True, payments={MAR: rupees(100_000)})
        assert p.interest_234c == ZERO

    def test_a_presumptive_default_is_one_month_not_ten(self) -> None:
        assert _plan(is_presumptive=True).interest_234c == rupees(1_000)

    def test_the_difference_is_explained(self) -> None:
        assert any("44AD" in n for n in _plan(is_presumptive=True).notes)


# ══ income nobody could have forecast ═══════════════════════════════════════

class TestExcusedIncome:
    """A capital gain in February was not foreseeable in June, and the Act does
    not pretend otherwise."""

    def test_a_february_gain_does_not_backdate_interest_to_june(self) -> None:
        gain_tax = rupees(60_000)
        p = plan_advance_tax(
            100_000, FY, has_business_income=True,
            excused_tax_by_date={date(2027, 2, 10): gain_tax},
            payments={
                JUN: rupees(6_000), SEP: rupees(18_000), DEC: rupees(30_000),
            },
        )
        # The first three instalments are computed on ₹40,000, not ₹1,00,000.
        assert [i.required for i in p.schedule[:3]] == [
            rupees(6_000), rupees(18_000), rupees(30_000)
        ]
        assert all(i.interest == ZERO for i in p.schedule[:3])

    def test_but_the_march_instalment_still_covers_it(self) -> None:
        """Excused from the earlier instalments, not from the year."""
        p = plan_advance_tax(
            100_000, FY, has_business_income=True,
            excused_tax_by_date={date(2027, 2, 10): rupees(60_000)},
            payments={JUN: rupees(6_000), SEP: rupees(18_000), DEC: rupees(30_000)},
        )
        assert p.schedule[3].excused == ZERO
        assert p.schedule[3].required == rupees(100_000)
        assert p.schedule[3].interest > ZERO

    def test_without_the_exclusion_the_same_taxpayer_is_overcharged(self) -> None:
        """The size of the error this rule prevents."""
        payments = {JUN: rupees(6_000), SEP: rupees(18_000), DEC: rupees(30_000)}
        excused = plan_advance_tax(
            100_000, FY, has_business_income=True, payments=payments,
            excused_tax_by_date={date(2027, 2, 10): rupees(60_000)},
        )
        naive = plan_advance_tax(100_000, FY, has_business_income=True,
                                 payments=payments)
        assert naive.interest_234c > excused.interest_234c
        assert excused.interest_234c == rupees(460)      # March only
        assert naive.interest_234c == rupees(1_990)     # 270+630+630+460
        assert naive.interest_234c - excused.interest_234c == rupees(1_530)

    def test_a_gain_that_arose_before_an_instalment_is_not_excused(self) -> None:
        """Excusal is keyed on when the income arose. An April gain was known
        by June."""
        p = plan_advance_tax(
            100_000, FY, has_business_income=True,
            excused_tax_by_date={date(2026, 4, 10): rupees(60_000)},
        )
        assert p.schedule[0].excused == ZERO
        assert p.schedule[0].required == rupees(15_000)


# ══ s.234B — a separate charge, not an alternative ══════════════════════════

class TestSection234B:
    def test_it_bites_below_ninety_percent(self) -> None:
        p = _plan(payments={MAR: rupees(89_000)})
        assert p.interest_234b > ZERO

    def test_ninety_percent_exactly_clears_it(self) -> None:
        p = _plan(payments={MAR: rupees(90_000)})
        assert p.interest_234b == ZERO

    def test_it_is_charged_on_the_whole_unpaid_balance(self) -> None:
        """Not on the amount below 90%. Paid ₹50,000 of ₹1,00,000, so the base
        is ₹50,000 — one month at 1% is ₹500."""
        p = _plan(payments={MAR: rupees(50_000)})
        assert p.interest_234b == rupees(500)

    def test_it_runs_from_the_first_of_april_with_april_as_month_one(self) -> None:
        """An assessment in July is four months — April, May, June, July."""
        p = _plan(payments={MAR: rupees(50_000)}, assessed_on=date(2027, 7, 20))
        assert p.interest_234b == rupees(2_000)

    def test_both_charges_can_apply_at_once(self) -> None:
        """234C is about when you paid within the year; 234B is about whether
        you reached 90% at all. They are not alternatives."""
        p = _plan()
        assert p.interest_234c > ZERO and p.interest_234b > ZERO
        assert p.total_interest == p.interest_234c + p.interest_234b

    def test_the_user_is_told_it_keeps_accruing(self) -> None:
        p = _plan(payments={MAR: rupees(50_000)})
        assert any("keeps accruing" in n for n in p.notes)


# ══ output ══════════════════════════════════════════════════════════════════

class TestOutput:
    def test_the_worksheet_replays(self) -> None:
        assert _plan(payments={MAR: rupees(50_000)}).trace.verify() == []

    def test_citations_name_the_provisions_actually_charged(self) -> None:
        charged = _plan()
        legacy = {c.legacy_section for c in charged.citations()}
        assert {"208", "211", "234B", "234C"} <= legacy

        clean = _plan(payments={
            JUN: rupees(15_000), SEP: rupees(30_000),
            DEC: rupees(30_000), MAR: rupees(25_000),
        })
        assert "234C" not in {c.legacy_section for c in clean.citations()}

    def test_the_2025_act_mapping_is_now_asserted_and_is_425(self) -> None:
        """234C is s.425, verified against the official CBDT navigator.

        Worth its own test because an earlier version of the alias file had
        this off by one — 234B at 425 and 234C at 426 — which would have cited
        the advance-tax deferment interest as the shortfall interest. The
        navigator: 234A 423, 234B 424, 234C 425.
        """
        c = next(x for x in _plan().citations() if x.legacy_section == "234C")
        assert c.section == "425"

    def test_serialises(self) -> None:
        d = _plan().to_dict()
        assert d["interest_234c"] == "5050.00"
        assert len(d["schedule"]) == 4
        assert d["citations"]

    def test_total_payable_is_the_tax_plus_the_interest(self) -> None:
        p = _plan()
        assert p.total_payable == p.liability + p.total_interest


# ══ golden corpus ═══════════════════════════════════════════════════════════

def _golden() -> list[dict]:
    import yaml

    path = pathlib.Path(__file__).parent / "golden" / "advance_tax" / "fy_2026_27.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


GOLDEN = _golden()


@pytest.mark.parametrize("case", GOLDEN, ids=[c["id"] for c in GOLDEN])
def test_golden_advance_tax(case: dict) -> None:
    payments = {
        date.fromisoformat(k): rupees(v) for k, v in (case.get("payments") or {}).items()
    }
    excused = {
        date.fromisoformat(k): rupees(v)
        for k, v in (case.get("excused_tax_by_date") or {}).items()
    }
    p = plan_advance_tax(
        case["total_tax"], FY,
        taxes_deducted=case.get("taxes_deducted", 0),
        payments=payments,
        age=case.get("age", 0),
        has_business_income=case.get("has_business_income", True),
        is_presumptive=case.get("is_presumptive", False),
        excused_tax_by_date=excused,
        assessed_on=(
            date.fromisoformat(case["assessed_on"]) if case.get("assessed_on") else None
        ),
    )
    actual = {
        "is_liable": p.is_liable,
        "liability": p.liability,
        "interest_234c": p.interest_234c,
        "interest_234b": p.interest_234b,
        "total_interest": p.total_interest,
        "instalments": len(p.schedule),
    }
    mismatches = []
    for key, want in case["expect"].items():
        assert key in actual, f"{case['id']}: unknown expectation {key!r}"
        got = actual[key]
        ok = got == want if isinstance(want, bool | int) and not isinstance(
            got, Money
        ) else got == rupees(want)
        if not ok:
            mismatches.append(f"    {key}: expected {want}, got {got}")
    if mismatches:
        pytest.fail(
            f"\n{case['id']}\n" + "\n".join(mismatches)
            + f"\n  verified against: {case['verified_against'].strip()}\n\n"
            + p.trace.render()
        )


def test_every_golden_case_shows_its_working() -> None:
    for case in GOLDEN:
        assert case.get("verified_against", "").strip(), (
            f"{case['id']} has no `verified_against`."
        )


# ══ s.244A — interest the department owes you ═══════════════════════════════

class TestRefundInterest:
    def test_the_rate_is_half_a_percent_a_month_not_one_percent_a_year(self) -> None:
        """The v1 defect. On a ₹50,000 refund granted in December — April to
        December inclusive, nine months — the correct figure is
        50,000 × 0.5% × 9 = ₹2,250. v1's "1% per annum simplified" gave ₹375,
        understating what the department owes by a factor of six."""
        r = refund_interest(50_000, FY, granted_on=date(2027, 12, 20))
        assert r.months == 9
        assert r.interest == rupees(2_250)

    def test_it_runs_from_the_first_of_april_with_april_as_month_one(self) -> None:
        r = refund_interest(50_000, FY, granted_on=date(2027, 4, 5))
        assert r.months == 1
        assert r.interest == rupees(250)

    def test_the_base_is_floored_under_rule_119a(self) -> None:
        r = refund_interest(8_489, FY, granted_on=date(2027, 4, 5))
        assert r.interest == pct_of(rupees(8_400), Decimal("0.005"))


class TestTheTenPercentProviso:
    """No interest where the refund is under 10% of the tax determined."""

    def test_a_small_refund_gets_no_interest_at_all(self) -> None:
        """₹8,000 against ₹1,00,000 of tax determined is 8% — under the floor,
        so the proviso denies interest entirely rather than reducing it."""
        r = refund_interest(8_000, FY, tax_determined=100_000,
                            granted_on=date(2027, 12, 20))
        assert r.interest == ZERO
        assert r.denied_by_proviso
        assert "under 10% of the tax determined" in r.caveats[0]

    def test_exactly_ten_percent_clears_the_floor(self) -> None:
        r = refund_interest(10_000, FY, tax_determined=100_000,
                            granted_on=date(2027, 12, 20))
        assert r.interest == rupees(450)          # 10,000 × 0.5% × 9
        assert not r.denied_by_proviso

    def test_the_denial_is_shown_on_the_worksheet_not_just_asserted(self) -> None:
        r = refund_interest(8_000, FY, tax_determined=100_000,
                            granted_on=date(2027, 12, 20))
        assert "proviso denies interest" in r.trace.render()

    def test_a_self_assessment_tax_refund_follows_the_case_law_and_says_so(
        self,
    ) -> None:
        """The proviso is written against clauses (a) and (aa), but appellate
        authority holds the embargo does not reach refunds of self-assessment
        tax. The engine follows that line and warns that the department may
        not — a divergence between text and case law is the user's to know
        about, not the engine's to resolve silently."""
        r = refund_interest(8_000, FY, tax_determined=100_000,
                            from_self_assessment_tax=True,
                            granted_on=date(2027, 12, 20))
        assert r.interest == rupees(360)
        assert not r.denied_by_proviso
        assert "appellate authority" in r.caveats[0]
        assert "take the other view" in r.caveats[0]

    def test_without_the_assessed_tax_the_proviso_cannot_be_checked(self) -> None:
        """Silence is not the same as "it does not apply". The caller who omits
        the assessed tax is told the figure is an upper bound."""
        r = refund_interest(8_000, FY, granted_on=date(2027, 12, 20))
        assert r.interest > ZERO
        assert "could not be checked" in r.caveats[0]
        assert "upper bound" in r.caveats[0]

    def test_a_refund_over_the_floor_carries_no_caveat_at_all(self) -> None:
        """Once the proviso is checked and cleared there is nothing to warn
        about, and a caveat on every result trains people to ignore them."""
        r = refund_interest(50_000, FY, tax_determined=100_000,
                            granted_on=date(2027, 12, 20))
        assert r.caveats == []
        assert r.interest == rupees(2_250)

    def test_the_worksheet_replays_and_cites_the_section(self) -> None:
        r = refund_interest(50_000, FY, granted_on=date(2027, 12, 20))
        assert r.trace.verify() == []
        assert any(c.legacy_section == "244A" for c in r.trace.citations())

    def test_total_receivable_is_the_refund_plus_the_interest(self) -> None:
        d = refund_interest(50_000, FY, granted_on=date(2027, 12, 20)).to_dict()
        assert d["total_receivable"] == "52250.00"
