"""The price intelligence rewrite — PRC-008.

Most of this feature was a deletion, so most of these tests assert that things
are GONE and cannot come back.
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

from backend.agents.price_intelligence import PriceIntelligenceAgent
from backend.core.rules.loader import RuleError, load_ruleset

SOURCE = pathlib.Path(
    __import__("backend.agents.price_intelligence", fromlist=["x"]).__file__
)
TEXT = SOURCE.read_text(encoding="utf-8")
TREE = ast.parse(TEXT)


def code_strings() -> list[str]:
    """String constants that are not docstrings.

    The docstrings in this module deliberately quote the old wrong figures —
    "ELSS at 12%", "10% LTCG" — to record what was removed and why. Scanning
    the raw text would flag the explanation as the offence.
    """
    docs = {
        ast.get_docstring(n, clean=False)
        for n in ast.walk(TREE)
        if isinstance(n, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
    }
    return [
        n.value for n in ast.walk(TREE)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
        and n.value not in docs
    ]


# ── what was deleted, and stays deleted ─────────────────────────────────────

def test_no_invented_yield_figures_remain():
    """FD at 7.5%, ELSS at 12%, gold at 6% — hardcoded floats presented to the
    user as though they had been computed."""
    floats = [
        n.value for n in ast.walk(TREE)
        if isinstance(n, ast.Constant) and isinstance(n.value, float)
    ]
    assert floats == [], floats


def test_the_cii_table_is_no_longer_hardcoded_in_the_agent():
    """It ended at FY 2024-25 and fell back to 254 or 363 for anything newer,
    so a 2025-26 acquisition indexed silently against 2015-16.

    Checked as "no dict literal maps financial-year strings to numbers",
    which is the shape of the thing that was removed. A flat ban on integers
    would catch the milliseconds conversion and teach nothing.
    """
    fy_like = re.compile(r"^\d{4}-\d{2}$")
    offenders = [
        ast.unparse(n) for n in ast.walk(TREE)
        if isinstance(n, ast.Dict)
        and any(
            isinstance(k, ast.Constant) and isinstance(k.value, str)
            and fy_like.match(k.value)
            for k in n.keys if k is not None
        )
    ]
    assert offenders == [], offenders


def test_the_agent_does_no_money_arithmetic():
    """Asserted here as well as in the AGT-001 ratchet, because this module is
    now in THIN_AGENTS and the reason should be visible from its own suite.

    Reuses the ratchet's own detector rather than a second, worse one — a
    private copy would drift and the two would disagree about what counts.
    """
    from backend.agents.tests.test_no_agent_arithmetic import (
        money_arithmetic_sites,
    )

    assert money_arithmetic_sites(SOURCE) == []


def test_no_marginal_slab_ladder_is_reimplemented():
    """The old file derived a slab rate from a hardcoded income ladder that no
    longer matched the actual slabs. Slabs live in the rule pack."""
    assert "300000" not in TEXT
    assert "annual_income" not in TEXT


# ── the refusal ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("query", [
    "which gives a better return, ELSS or FD?",
    "compare post-tax yields for me",
    "should I buy sovereign gold bonds",
    "what is the best investment for tax saving",
])
async def test_a_yield_comparison_is_declined_rather_than_answered(query):
    """Ranking investment products by projected return for a named individual
    is personalised investment advice. AGT-006 refuses it when a user asks; a
    code path that VOLUNTEERED it made no sense to keep."""
    out = await PriceIntelligenceAgent().execute(query, {})
    assert out.status == "declined"
    assert out.result["calculation_type"] == "declined_out_of_scope"
    assert "SEBI" in out.result["explanation"]


@pytest.mark.asyncio
async def test_the_refusal_says_what_it_can_do_instead():
    """A refusal that only refuses teaches the user nothing about where the
    line is."""
    out = await PriceIntelligenceAgent().execute("compare yields", {})
    assert len(out.result["what_this_can_do"]) >= 2
    assert any("tax treatment" in s.lower()
               for s in out.result["what_this_can_do"])


@pytest.mark.asyncio
async def test_sgb_position_is_stated_and_the_old_recommendation_disowned():
    """v1 recommended buying these. Primary issuance stopped in February 2024,
    so a user acting on it would find there is nothing to buy."""
    out = await PriceIntelligenceAgent().execute("should I buy SGBs?", {})
    text = out.result["sovereign_gold_bonds"]
    assert "February 2024" in text
    assert "nothing to buy at primary issue" in text
    assert "tradable on" in text          # the secondary position, stated
    assert "earlier version of this product recommended" in text


@pytest.mark.asyncio
async def test_no_string_the_user_sees_recommends_buying_anything():
    """Scoped to what is actually rendered, not to every constant in the file.

    The query-detection list contains "best investment" because that is a
    phrase the agent must RECOGNISE in order to decline it, and flagging that
    would be flagging the guardrail for naming what it guards against.
    """
    forbidden = re.compile(
        r"\b(?:you should buy|highly tax-efficient|offers the highest|"
        r"best (?:investment|option) (?:is|for you)|we recommend)\b",
        re.IGNORECASE,
    )
    agent = PriceIntelligenceAgent()
    shown: list[str] = []
    for query, ctx in [("compare yields", {}), ("index my gain", {})]:
        out = await agent.execute(query, ctx)
        shown.extend(
            v for v in out.result.values() if isinstance(v, str)
        )
        shown.extend(
            s for v in out.result.values() if isinstance(v, list)
            for s in v if isinstance(s, str)
        )
    assert shown
    for value in shown:
        assert not forbidden.search(value), value


# ── indexation, routed rather than reimplemented ────────────────────────────

@pytest.mark.asyncio
async def test_missing_inputs_are_named_rather_than_assumed():
    """The old file defaulted annual income to ₹10,00,000 and the CII to 254.
    The acquisition date alone decides whether the 20%-with-indexation
    election exists at all, so guessing it is not a small thing."""
    out = await PriceIntelligenceAgent().execute("index my property gain", {})
    assert out.status == "needs_input"
    assert set(out.result["missing_fields"]) == {
        "acquired_on", "sold_on", "cost", "consideration",
    }


@pytest.mark.asyncio
async def test_without_the_tool_layer_the_agent_says_so_rather_than_computing():
    out = await PriceIntelligenceAgent().execute("capital gains", {
        "acquired_on": "2015-06-01", "sold_on": "2026-06-01",
        "cost": 2000000, "consideration": 8000000,
    })
    assert out.status == "error"
    assert "does not compute figures itself" in out.result["explanation"]


@pytest.mark.asyncio
async def test_a_disposal_is_computed_by_the_engine_and_the_election_explained():
    calls: list[dict] = []

    class FakeTools:
        def list_tools(self):
            return ["calculate_capital_gains"]

        async def execute_tool(self, name, **kwargs):
            calls.append({"name": name, **kwargs})
            return {"success": True, "result": {"total_tax": "125000"}}

    out = await PriceIntelligenceAgent().execute(
        "what is my capital gains tax",
        {"acquired_on": "2015-06-01", "sold_on": "2026-06-01",
         "cost": 2000000, "consideration": 8000000},
        tools=FakeTools(),
    )
    assert out.status == "success"
    assert calls[0]["name"] == "calculate_capital_gains"
    assert calls[0]["disposals"][0]["acquired_on"] == "2015-06-01"
    assert "20% with indexation" in out.result["recommendations"][0]
    assert "23 July 2024" in out.result["recommendations"][0]


# ── the index now lives where every other rate does ─────────────────────────

def test_the_official_index_is_in_the_rule_pack():
    """Notification 70/2025, read from incometaxindia.gov.in on 2026-08-13."""
    rs = load_ruleset("2026-27")
    assert rs.cii("2001-02") == 100
    assert rs.cii("2024-25") == 363
    assert rs.cii("2025-26") == 376
    assert rs.cii("2026-27") == 384


def test_an_unknown_year_raises_instead_of_falling_back():
    """The behaviour the hardcoded table did not have. `.get(year, 254)` is
    how a 2025-26 acquisition got indexed against 2015-16 with nothing to
    notice."""
    with pytest.raises(RuleError, match="no Cost Inflation Index"):
        load_ruleset("2026-27").cii("2030-31")
