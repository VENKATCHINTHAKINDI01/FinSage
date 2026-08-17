"""AIS reconciliation — DOC-003.

The acceptance criterion is **zero false negatives on a seeded mismatch set**.
`test_no_false_negatives_across_the_seeded_set` is that criterion, executed.

Income present in the AIS and absent from the return is the single most common
trigger for a tax notice. Missing one is the failure that matters; flagging one
unnecessarily costs the user a minute.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from backend.services.parsers.ais import (
    AIS,
    AISEntry,
    AISParseError,
    Category,
    Severity,
    classify,
    parse_ais_json,
    reconcile,
)

# ── fixtures ────────────────────────────────────────────────────────────────

AIS_JSON = json.dumps({
    "pan": "ABCDE1234F",
    "financialYear": "2026-27",
    "information": [
        {
            "informationCategory": "Salary",
            "entries": [
                {"informationDescription": "Salary received",
                 "informationSource": "ACME SOFTWARE PRIVATE LIMITED",
                 "amount": 1275000},
            ],
        },
        {
            "informationCategory": "Interest",
            "entries": [
                {"informationDescription": "Interest from savings bank",
                 "informationSource": "HDFC BANK", "amount": 12500},
                {"informationDescription": "Interest from deposit",
                 "informationSource": "HDFC BANK", "amount": 68000},
            ],
        },
        {
            "informationCategory": "Dividend",
            "entries": [
                {"informationDescription": "Dividend received",
                 "informationSource": "INFOSYS LIMITED", "amount": 18000},
            ],
        },
        {
            "informationCategory": "Securities",
            "entries": [
                {"informationDescription": "Sale of securities",
                 "informationSource": "ZERODHA BROKING", "amount": 1160000},
            ],
        },
        {
            "informationCategory": "TDS",
            "entries": [
                {"informationDescription": "Tax deducted at source",
                 "informationSource": "ACME SOFTWARE", "amount": 74100},
            ],
        },
    ],
})


def _ais(**totals: int) -> AIS:
    """Build an AIS directly, for reconciliation tests."""
    return AIS(
        fy="2026-27",
        entries=[
            AISEntry(Category(cat), Decimal(amount), f"{cat} entry", "TEST BANK")
            for cat, amount in totals.items()
        ],
    )


# ── parsing ─────────────────────────────────────────────────────────────────

class TestParsing:
    def test_walks_a_nested_export(self) -> None:
        ais = parse_ais_json(AIS_JSON)
        assert ais.pan == "ABCDE1234F"
        assert ais.fy == "2026-27"
        # salary + savings interest + deposit interest + dividend
        # + securities + TDS
        assert len(ais.entries) == 6

    def test_categorises_entries(self) -> None:
        totals = parse_ais_json(AIS_JSON).by_category()
        assert totals[Category.SALARY] == Decimal(1275000)
        assert totals[Category.INTEREST_SAVINGS] == Decimal(12500)
        assert totals[Category.INTEREST_DEPOSITS] == Decimal(68000)
        assert totals[Category.SECURITIES] == Decimal(1160000)

    def test_reporting_sources_are_kept(self) -> None:
        """So a finding can say WHO reported it — 'HDFC reported ₹68,000' is
        actionable in a way that a bare number is not."""
        ais = parse_ais_json(AIS_JSON)
        assert "HDFC BANK" in ais.sources_for(Category.INTEREST_DEPOSITS)

    def test_an_empty_statement_is_refused(self) -> None:
        """Reporting a clean reconciliation against an unread statement would
        be worse than failing."""
        with pytest.raises(AISParseError, match="refusing to report a clean"):
            parse_ais_json('{"pan": "ABCDE1234F"}')

    def test_a_non_object_payload_is_refused(self) -> None:
        with pytest.raises(AISParseError):
            parse_ais_json("[1, 2, 3]")

    def test_uncategorised_entries_are_reported_not_dropped(self) -> None:
        ais = parse_ais_json(json.dumps({
            "financialYear": "2026-27",
            "information": [{"informationDescription": "Some novel category",
                             "amount": 5000}],
        }))
        assert any("could not be categorised" in w for w in ais.warnings)


@pytest.mark.parametrize(
    "description,expected",
    [
        ("Interest from savings bank", Category.INTEREST_SAVINGS),
        ("Interest from deposit", Category.INTEREST_DEPOSITS),
        ("Sale of securities", Category.SECURITIES),
        ("Sale of immovable property", Category.IMMOVABLE_PROPERTY),
        ("Rent received", Category.RENT),
        ("Tax deducted at source", Category.TDS),
        ("Something unheard of", Category.OTHER),
    ],
)
def test_classification(description: str, expected: Category) -> None:
    assert classify(description) is expected


def test_the_longest_hint_wins() -> None:
    """'interest from deposit' must not be shadowed by a bare 'interest'."""
    assert classify("Interest from deposit with bank") is Category.INTEREST_DEPOSITS


# ══ THE ACCEPTANCE CRITERION ════════════════════════════════════════════════

# Each case seeds income into the AIS that the return omits entirely. Every one
# must come back HIGH. A miss here is a tax notice the user did not see coming.
SEEDED_OMISSIONS = [
    ({"interest_savings": 12500}, Category.INTEREST_SAVINGS),
    ({"interest_deposits": 68000}, Category.INTEREST_DEPOSITS),
    ({"dividend": 18000}, Category.DIVIDEND),
    ({"sale_of_securities": 1160000}, Category.SECURITIES),
    ({"sale_of_mutual_funds": 310000}, Category.MUTUAL_FUNDS),
    ({"sale_of_immovable_property": 9000000}, Category.IMMOVABLE_PROPERTY),
    ({"rent_received": 240000}, Category.RENT),
    ({"business_receipts": 1500000}, Category.BUSINESS_RECEIPTS),
    ({"foreign_remittance": 500000}, Category.FOREIGN_REMITTANCE),
]


@pytest.mark.parametrize("ais_totals,expected", SEEDED_OMISSIONS,
                         ids=[c.value for _, c in SEEDED_OMISSIONS])
def test_no_false_negatives_across_the_seeded_set(
    ais_totals: dict[str, int], expected: Category
) -> None:
    """DOC-003's acceptance criterion, executed.

    Income the AIS records and the return omits must ALWAYS surface as HIGH.
    """
    result = reconcile(_ais(**ais_totals), declared={Category.SALARY: 1275000})

    matching = [f for f in result.high if f.category is expected]
    assert matching, (
        f"MISSED: {expected.label} appears in the AIS and not in the return, "
        f"and was not flagged HIGH. This is the notice the user does not see "
        f"coming."
    )
    assert matching[0].declared_amount == Decimal(0)
    assert "do not simply ignore it" in matching[0].action.lower()


def test_every_omission_is_caught_when_they_all_occur_at_once() -> None:
    combined = {cat: amount for totals, _ in SEEDED_OMISSIONS
                for cat, amount in totals.items()}
    result = reconcile(_ais(**combined), declared={Category.SALARY: 1275000})

    assert len(result.high) == len(SEEDED_OMISSIONS)
    assert not result.is_clean
    assert "most common trigger for a notice" in result.summary()


def test_an_absent_category_is_not_treated_as_declared_zero() -> None:
    """The distinction the whole module turns on. Silence in the return is
    'not declared', not 'declared as nil'."""
    result = reconcile(_ais(dividend=18000), declared={})
    assert result.high and result.high[0].category is Category.DIVIDEND


def test_explicitly_declaring_zero_is_still_a_mismatch_not_an_omission() -> None:
    """Different severity, because the taxpayer has at least engaged with it."""
    result = reconcile(_ais(dividend=18000), declared={Category.DIVIDEND: 0})
    finding = next(f for f in result.findings if f.category is Category.DIVIDEND)
    assert finding.severity is Severity.MEDIUM


# ── the other direction, and materiality ────────────────────────────────────

def test_declaring_more_than_the_ais_is_low_not_high() -> None:
    """Over-declaring is not a risk. Treating it as one would train people to
    ignore the alerts that matter."""
    result = reconcile(_ais(dividend=18000), declared={Category.DIVIDEND: 25000})
    finding = next(f for f in result.findings if f.category is Category.DIVIDEND)
    assert finding.severity is Severity.LOW
    assert "No action needed" in finding.action


def test_a_rounding_difference_is_not_a_finding() -> None:
    result = reconcile(_ais(dividend=18000), declared={Category.DIVIDEND: 17950})
    finding = next(f for f in result.findings if f.category is Category.DIVIDEND)
    assert finding.severity is Severity.INFO
    assert result.is_clean


def test_an_exact_match_is_clean() -> None:
    result = reconcile(
        _ais(salary=1275000, dividend=18000),
        declared={Category.SALARY: 1275000, Category.DIVIDEND: 18000},
    )
    assert result.is_clean
    assert "agrees with the AIS" in result.summary()


def test_tds_is_a_credit_and_is_not_reconciled_as_income() -> None:
    """Reconciling TDS as income would double count and produce a nonsense
    HIGH finding on every single return."""
    result = reconcile(_ais(tax_deducted=74100), declared={})
    assert not any(f.category is Category.TDS for f in result.findings)
    assert result.is_clean


# ── AIS is not gospel ───────────────────────────────────────────────────────

def test_a_securities_finding_explains_consideration_versus_gain() -> None:
    """The most common false alarm in the whole product. AIS reports SALE
    VALUE; the return declares the GAIN. Flagging that without explaining it
    would frighten people into over-declaring."""
    result = reconcile(_ais(sale_of_securities=1160000), declared={})
    finding = result.high[0]
    assert any("CONSIDERATION" in e for e in finding.benign_explanations)
    assert any("GAIN" in e for e in finding.benign_explanations)


def test_property_findings_mention_joint_ownership() -> None:
    result = reconcile(_ais(sale_of_immovable_property=9000000), declared={})
    assert any("jointly owned" in e for e in result.high[0].benign_explanations)


def test_rent_findings_mention_the_thirty_percent_deduction() -> None:
    result = reconcile(_ais(rent_received=240000), declared={})
    assert any("30%" in e for e in result.high[0].benign_explanations)


def test_the_action_points_at_ais_feedback_not_just_at_paying_more() -> None:
    """AIS genuinely contains errors. The right action is sometimes to correct
    the AIS, not the return."""
    result = reconcile(_ais(dividend=18000), declared={})
    assert "feedback" in result.high[0].action.lower()


# ── ordering, serialisation, end to end ─────────────────────────────────────

def test_findings_are_ordered_most_serious_first() -> None:
    result = reconcile(
        _ais(salary=1275000, dividend=18000, rent_received=240000),
        declared={Category.SALARY: 1275000, Category.DIVIDEND: 25000},
    )
    order = [Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO]
    positions = [order.index(f.severity) for f in result.findings]
    assert positions == sorted(positions)


def test_serialises() -> None:
    d = reconcile(_ais(dividend=18000), declared={}).to_dict()
    assert d["high_severity"] == 1
    assert d["findings"][0]["category"] == "dividend"
    assert d["findings"][0]["difference"] == "18000"


def test_end_to_end_from_the_portal_download() -> None:
    """A real-shaped AIS export against a partially complete return."""
    ais = parse_ais_json(AIS_JSON)
    result = reconcile(ais, declared={
        Category.SALARY: 1275000,
        Category.INTEREST_SAVINGS: 12500,
        # deposits, dividend and securities all omitted
    })

    flagged = {f.category for f in result.high}
    assert flagged == {
        Category.INTEREST_DEPOSITS, Category.DIVIDEND, Category.SECURITIES
    }
    assert "HDFC BANK" in next(
        f for f in result.high if f.category is Category.INTEREST_DEPOSITS
    ).message


@pytest.mark.skip(
    reason="DOC-003 acceptance also requires a real AIS download. The portal's "
           "JSON shape varies between versions and the fixture here is "
           "reconstructed, not captured."
)
def test_against_a_real_ais_download() -> None:
    """Deliberately visible. DOC-003 does not reach `verified` without this."""
