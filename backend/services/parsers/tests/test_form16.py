"""Form 16 parser — DOC-001.

Fixtures are synthetic and deliberately varied, because employers word the same
line differently and lay it out differently. Real-sample validation is still
outstanding; see the note at the bottom of this file.

The tests that matter most are the refusals. A parser that quietly mis-reads
gross salary produces an answer that is confidently, precisely wrong.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.services.parsers.form16 import (
    Confidence,
    Form16ParseError,
    parse_text,
)

# ── fixtures ────────────────────────────────────────────────────────────────

CLEAN = """
FORM NO. 16
Certificate under section 203 of the Income-tax Act
Assessment Year 2027-28

Name and address of the Employer          Name and address of the Employee
ACME SOFTWARE PRIVATE LIMITED             R KUMAR
TAN of the Deductor  BLRA12345F           PAN of the Employee  ABCDE1234F

PART B - ANNEXURE
1. Gross Salary
   (a) Salary as per provisions contained in section 17(1)     1275000.00
2. Total amount of exemption claimed under section 10           0.00
3. Gross Salary                                                 1275000.00
4. Deductions under section 16
   (a) Standard deduction under section 16(ia)                  75000.00
   (b) Tax on employment under section 16(iii)                  2400.00
5. Income chargeable under the head Salaries                    1197600.00
6. Gross total income                                           1197600.00
7. Deductions under Chapter VI-A
   (a) Section 80C                                              150000.00
   (b) Section 80D                                              25000.00
   Aggregate of deductible amount under Chapter VI-A            175000.00
8. Total taxable income                                         1022600.00
9. Tax payable                                                  0.00
10. Total amount of tax deducted at source                      0.00
"""

# Same document, a different employer's wording and a rupee-symbol format.
ALTERNATE_WORDING = """
Form 16 Part B
Assessment Year 2027-28
PAN of the Employee: XYZAB9876C
TAN: MUMA98765K

Gross Salary                                        ₹ 18,00,000
Less: Allowances to the extent exempt under section 10   ₹ 1,80,000
Standard deduction                                  ₹ 75,000
Professional tax                                    ₹ 2,500
Income chargeable under the head Salaries           ₹ 15,42,500
Section 80C                                         ₹ 1,50,000
Section 80CCD(1B)                                   ₹ 50,000
Total deduction under Chapter VI-A                  ₹ 2,00,000
Total income                                        ₹ 13,42,500
Net tax payable                                     ₹ 1,06,470
Tax deducted at source                              ₹ 1,06,470
"""

# The figure sits on the line below its label — a common two-column layout.
AMOUNT_ON_NEXT_LINE = """
FORM NO. 16
Assessment Year 2027-28
Gross Salary
   900000.00
Standard deduction under section 16(ia)
   75000.00
Total taxable income
   825000.00
Total amount of tax deducted at source
   35000.00
"""


# ── the happy path ──────────────────────────────────────────────────────────

class TestCleanForm:
    def test_identifiers(self) -> None:
        f = parse_text(CLEAN)
        assert f.assessment_year == "2027-28"
        assert f.employee_pan == "ABCDE1234F"
        assert f.employer_tan == "BLRA12345F"

    def test_amounts(self) -> None:
        f = parse_text(CLEAN)
        assert f.amount("gross_salary") == Decimal("1275000.00")
        assert f.amount("standard_deduction") == Decimal("75000.00")
        assert f.amount("professional_tax") == Decimal("2400.00")
        assert f.amount("net_salary") == Decimal("1197600.00")
        assert f.amount("taxable_income") == Decimal("1022600.00")

    def test_chapter_via_lines_are_itemised_not_just_totalled(self) -> None:
        """The profile needs the individual sections, not one lump."""
        f = parse_text(CLEAN)
        assert f.deductions["80C"].value == Decimal("150000.00")
        assert f.deductions["80D"].value == Decimal("25000.00")

    def test_it_reconciles(self) -> None:
        """1275000 − 0 − 75000 − 2400 = 1197600, matching the stated net."""
        assert parse_text(CLEAN).check_internal_consistency() == []

    def test_usable(self) -> None:
        f = parse_text(CLEAN)
        assert f.is_usable
        assert f.missing == []


def test_alternate_employer_wording_and_rupee_format() -> None:
    f = parse_text(ALTERNATE_WORDING)
    assert f.amount("gross_salary") == Decimal("1800000")
    assert f.amount("exempt_allowances") == Decimal("180000")
    assert f.deductions["80CCD_1B"].value == Decimal("50000")
    assert f.amount("tds_deducted") == Decimal("106470")


def test_amount_on_the_following_line_is_found_but_marked_for_review() -> None:
    """Found, because the layout is common. Marked, because 'the number just
    below' is a guess about layout rather than a reading of a label."""
    f = parse_text(AMOUNT_ON_NEXT_LINE)
    assert f.amount("gross_salary") == Decimal("900000.00")
    assert f.fields["gross_salary"].confidence is Confidence.REVIEW
    assert "following line" in f.fields["gross_salary"].note


# ── the refusals, which matter most ─────────────────────────────────────────

class TestRefusals:
    def test_empty_document(self) -> None:
        with pytest.raises(Form16ParseError, match="empty"):
            parse_text("")

    def test_a_document_that_is_not_a_form_16(self) -> None:
        """Better to refuse than to scrape plausible numbers off a payslip,
        a bank statement, or somebody's rent agreement."""
        with pytest.raises(Form16ParseError, match="does not look like a Form 16"):
            parse_text("INVOICE\nTotal due: 45,000\nThank you for your business")

    def test_a_scanned_pdf_says_so_rather_than_returning_nothing(self) -> None:
        from backend.services.parsers.form16 import parse_pdf

        with pytest.raises(Form16ParseError):
            parse_pdf("/nonexistent/scan.pdf")


class TestNeverSilentlyGuesses:
    def test_a_missing_essential_field_is_reported(self) -> None:
        f = parse_text("FORM NO. 16\nAssessment Year 2027-28\nGross Salary  500000")
        assert "taxable_income" in f.missing
        assert not f.is_usable
        assert any("taxable income" in w for w in f.warnings)

    def test_an_ambiguous_line_is_downgraded_not_resolved(self) -> None:
        """Several figures on one row is a running-total column. The rightmost
        is conventionally the value — conventionally is not certainly."""
        f = parse_text(
            "FORM NO. 16\nAssessment Year 2027-28\n"
            "Gross Salary   500000.00   1275000.00\n"
            "Total taxable income  1000000\nTax deducted at source 5000"
        )
        got = f.fields["gross_salary"]
        assert got.confidence is Confidence.REVIEW
        assert "2 amounts on this line" in got.note

    def test_four_digit_years_are_not_mistaken_for_amounts(self) -> None:
        f = parse_text(
            "FORM NO. 16\nAssessment Year 2027-28\n"
            "Gross Salary for the year 2026 was 1275000\n"
            "Total taxable income 1200000\nTax deducted at source 0"
        )
        assert f.amount("gross_salary") == Decimal("1275000")


class TestConsistencyIsCheckedNotAssumed:
    def test_components_that_do_not_add_up_are_reported(self) -> None:
        """The document states both parts and totals, so it checks itself. If
        they disagree, something was misread — say so rather than picking."""
        broken = CLEAN.replace(
            "5. Income chargeable under the head Salaries                    1197600.00",
            "5. Income chargeable under the head Salaries                    1100000.00",
        )
        problems = parse_text(broken).check_internal_consistency()
        assert any("do not reconcile" in p for p in problems)
        assert any("97,600" in p for p in problems)

    def test_chapter_via_lines_that_do_not_sum_are_reported(self) -> None:
        broken = CLEAN.replace(
            "Aggregate of deductible amount under Chapter VI-A            175000.00",
            "Aggregate of deductible amount under Chapter VI-A            250000.00",
        )
        problems = parse_text(broken).check_internal_consistency()
        assert any("Chapter VI-A lines sum to" in p for p in problems)


# ── what reaches the profile ────────────────────────────────────────────────

class TestProfileDraft:
    def test_only_high_confidence_figures_are_offered(self) -> None:
        draft = parse_text(CLEAN).to_profile_draft()
        assert draft["salary"] == "1275000.00"
        assert draft["deductions"]["80C"] == "150000.00"
        assert draft["pan"] == "ABCDE1234F"

    def test_a_review_grade_figure_is_withheld_from_the_draft(self) -> None:
        """It appears in `needs_confirmation` instead. Nothing enters a
        calculation without the user having seen it."""
        f = parse_text(AMOUNT_ON_NEXT_LINE)
        assert "salary" not in f.to_profile_draft()
        assert "gross_salary" in [x.name for x in f.needs_confirmation]

    def test_every_field_carries_the_line_it_came_from(self) -> None:
        """So the UI can show the extraction against its source rather than
        asking the user to trust it."""
        f = parse_text(CLEAN)
        assert "1275000.00" in f.fields["gross_salary"].source_line

    def test_serialises(self) -> None:
        d = parse_text(CLEAN).to_dict()
        assert d["assessment_year"] == "2027-28"
        assert d["is_usable"] is True
        assert d["fields"]["gross_salary"]["confidence"] == "high"


# ── outstanding ─────────────────────────────────────────────────────────────

@pytest.mark.skip(
    reason="DOC-001 acceptance requires real employer Form 16 samples. These "
           "fixtures are synthetic; format variance across real employers is "
           "the main risk and is not yet measured."
)
def test_against_real_employer_samples() -> None:
    """Placeholder, deliberately visible.

    DOC-001 does not move to `verified` until this runs against real documents
    from several employers. A parser proven only on fixtures its own author
    wrote has been proven against its author's assumptions.
    """
