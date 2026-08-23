"""Figures the legacy agents used to invent — AGT-001.

The ratchet in `test_no_agent_arithmetic.py` counts arithmetic SITES. That
stops the debt growing, but it cannot tell a harmless sum from a fabricated
tax rate, and a count going down is not evidence that the answers got right.

These assert the answers. Each one fails against the code as it stood before
2026-08-23, with the wrong figure named in the test so that a future change
reintroducing it is recognisable rather than merely red.
"""

from __future__ import annotations

import pytest

from backend.agents.compliance_checker import ComplianceCheckerAgent
from backend.agents.itr_helper import ITRHelperAgent


class _Ctx(dict):
    """A user context with nothing in it but income."""


# ── the flat 20% ────────────────────────────────────────────────────────────

def test_advance_tax_is_not_twenty_percent_of_gross_income():
    """₹6,00,000 under the new regime owes nothing, after s.87A.

    The old code reported `600000 * 0.20` = ₹1,20,000 and told the user
    advance tax was due on it. The error is not a rounding difference — it is
    the entire s.87A rebate, the standard deduction and the slabs, missing.
    """
    agent = ITRHelperAgent.__new__(ITRHelperAgent)
    result = ITRHelperAgent._validate_advance_tax(
        agent, {"annual_income": 600000, "advance_tax_paid": 0}, {},
    )

    assert result["estimated_tax"] == 0.0
    assert result["advance_tax_required"] is False
    assert result["estimated_tax"] != 120000.0  # the figure it used to give


def test_advance_tax_instalments_follow_the_statute_not_a_quarter_each():
    """15 / 45 / 75 / 100, not 25 / 50 / 75 / 100.

    s.211 of the 1961 Act and s.404 of the 2025 Act, confirmed against the
    department's own advance-tax page. The old schedule overstated the first
    two instalments by ten and five points. This one errs toward paying early
    — but it is still a number the agent made up, and the same code shipping
    the reverse error is a one-character change away.
    """
    agent = ITRHelperAgent.__new__(ITRHelperAgent)
    result = ITRHelperAgent._validate_advance_tax(
        agent, {"annual_income": 1800000, "advance_tax_paid": 0}, {},
    )

    percents = [row["cumulative_percent"] for row in result["schedule"]]
    assert percents == ["15%", "45%", "75%", "100%"]

    total = float(result["estimated_tax"])
    first = float(result["schedule"][0]["required"])
    # 15% of the liability, not 25%.
    assert first == pytest.approx(total * 0.15, rel=1e-6)
    assert first != pytest.approx(total * 0.25, rel=1e-6)


def test_the_instalment_dates_belong_to_the_financial_year():
    """June, September and December fall in the FY; March in the next year."""
    agent = ITRHelperAgent.__new__(ITRHelperAgent)
    result = ITRHelperAgent._validate_advance_tax(
        agent, {"annual_income": 1800000, "fy": "2026-27"}, {},
    )
    due = [row["due_on"] for row in result["schedule"]]
    assert due == ["2026-06-15", "2026-09-15", "2026-12-15", "2027-03-15"]


# ── the red flag that fired on a fabricated baseline ────────────────────────

def test_the_tds_baseline_is_computed_not_assumed():
    """A compliance warning must not be triggered by an invented number.

    The baseline was `annual_income * 0.20`. On ₹6,00,000 that is ₹1,20,000
    against a real liability of nothing, so a user whose TDS was correct got
    a red "TDS paid vs 26AS mismatch". A false alarm in a compliance tone of
    voice is worse than silence: it teaches the user to dismiss the next one.
    """
    baseline = ComplianceCheckerAgent._estimated_tax(
        600000, {"regime": "new"}, {},
    )
    assert baseline == 0.0
    assert baseline != 120000.0


def test_an_unavailable_baseline_produces_no_flag_rather_than_a_guess():
    """If the engine cannot answer, the honest position is no comparison.

    A missing warning is recoverable. A confident wrong one is not.
    """
    baseline = ComplianceCheckerAgent._estimated_tax(
        600000, {"fy": "1999-2000"}, {},  # no rule pack for that year
    )
    assert baseline == 0.0
