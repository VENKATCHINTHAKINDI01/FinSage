"""No agent performs arithmetic on money — AGT-001.

The governing rule of the whole system is that no rupee figure shown to a user
may originate from a language model. `numeric_provenance` enforces the output
side. This enforces the *code* side: an agent that computes tax itself is a
second engine, and a second engine disagrees with the first.

Why this is a shrinking baseline rather than a clean assertion
--------------------------------------------------------------
Eleven v1 agent modules still do their own arithmetic — `advanced_calculator`
alone has a hardcoded `(income_tax + surcharge) * 0.04` cess. Rewriting them is
AGT-001 proper and is not yet done. Asserting zero today would fail the build;
asserting nothing would let the number grow quietly while the registry claimed
progress.

So the count is pinned. It may fall, never rise. Every module rebuilt in this
programme is already at zero and is listed explicitly, so a regression in one of
them fails immediately rather than hiding inside a tolerance.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

AGENTS = pathlib.Path(__file__).resolve().parents[1]

# Modules rebuilt to the thin-agent standard. These are asserted at ZERO — the
# tolerance below does not apply to them.
THIN_AGENTS = {
    "analyst.py",
    "reviewer_ca.py",
    "reviewer_risk.py",
    "pipeline.py",
    "review_protocol.py",
    "base_agent.py",
    "freshness.py",
    "benefits_discovery.py",
    "eligibility_verifier.py",
    "wealth_planner.py",
    # PRC-008: rewritten from 8 arithmetic sites to none. The yield
    # comparison that produced most of them was deleted rather than fixed —
    # ranking investments by projected return is SEBI territory — and the
    # indexation branch now routes to the core engine through a tool.
    "price_intelligence.py",
    # AGT-001: bridge from intent detection to the pipeline. All computation
    # is delegated to backend.core through TaxCalculationEngine.
    "intent_bridge.py",
    # AGT-001 (2026-08-18): _generate_strategies' LLM prompt no longer asks
    # for a rupee estimated_savings — every figure now comes from
    # calculate_deduction_impact against a scheme's real statutory limit
    # (get_scheme_details), never from the model's guess or a flat-rate
    # multiplier. Strategies with no fixed limit to test against (no
    # scheme_code) carry savings=None rather than a fabricated number.
    "tax_optimizer.py",
}

# v1 modules awaiting the AGT-001 rewrite, with today's count. RATCHET: these
# may only go down. Lower a number when you fix a module; never raise one.
LEGACY_BUDGET = {
    "advanced_calculator.py": 24,
    "tools.py": 13,
    "compliance_checker.py": 6,
    "income_classifier.py": 6,
    "itr_helper.py": 6,
    "tax_strategy.py": 4,
    "deduction_hunter.py": 2,
    "cross_border_tax.py": 1,
    "tax_agent.py": 1,
}

MONEY_WORDS = (
    "tax", "income", "amount", "saving", "deduction", "salary", "cess",
    "surcharge", "rupee", "rebate",
)


def money_arithmetic_sites(path: pathlib.Path) -> list[str]:
    """Binary arithmetic whose source text mentions money.

    A deliberately blunt heuristic. It over-reports — a loop index added to a
    variable called `tax_row` counts — and that is the right direction for a
    guard: the cost of a false positive is a one-line justification, the cost of
    a false negative is a second tax engine nobody noticed.
    """
    src = path.read_text(encoding="utf-8")
    found = []
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.BinOp):
            continue
        if not isinstance(node.op, ast.Add | ast.Sub | ast.Mult | ast.Div):
            continue
        segment = (ast.get_source_segment(src, node) or "").lower()
        if any(word in segment for word in MONEY_WORDS):
            found.append(f"line {node.lineno}: {segment[:70]}")
    return found


def agent_modules() -> list[pathlib.Path]:
    return sorted(
        p for p in AGENTS.rglob("*.py")
        if "tests" not in p.parts and p.name != "__init__.py"
    )


@pytest.mark.parametrize("name", sorted(THIN_AGENTS))
def test_a_rebuilt_agent_does_no_money_arithmetic(name: str) -> None:
    """Zero, with no tolerance. These modules route every figure through the
    tools adapter, and the whole point of rebuilding them was to stop them
    computing."""
    path = AGENTS / name
    if not path.exists():
        pytest.skip(f"{name} not present")
    sites = money_arithmetic_sites(path)
    assert not sites, (
        f"{name} has acquired money arithmetic. Route it through "
        f"backend/tools/calculation.py instead:\n  " + "\n  ".join(sites)
    )


@pytest.mark.parametrize("name,budget", sorted(LEGACY_BUDGET.items()))
def test_legacy_agent_arithmetic_never_grows(name: str, budget: int) -> None:
    """The ratchet. AGT-001 is the work of getting these to zero; this stops
    them getting worse while that is pending."""
    path = AGENTS / name
    if not path.exists():
        pytest.skip(f"{name} has been deleted — remove it from LEGACY_BUDGET")
    count = len(money_arithmetic_sites(path))
    assert count <= budget, (
        f"{name} now has {count} money-arithmetic sites, up from {budget}. "
        f"Agents must not acquire tax knowledge — route through the tools "
        f"adapter."
    )
    assert count == budget or count < budget, "unreachable"
    if count < budget:
        pytest.fail(
            f"{name} is down to {count} sites from {budget} — good. Lower the "
            f"budget in LEGACY_BUDGET to lock the improvement in."
        )


def test_every_agent_module_is_accounted_for() -> None:
    """A new agent file must be classified, not silently exempt.

    Without this, adding `backend/agents/new_calculator.py` full of arithmetic
    would pass the whole suite.
    """
    known = THIN_AGENTS | set(LEGACY_BUDGET)
    unlisted = {
        p.name for p in agent_modules() if p.name not in known
    }
    assert not unlisted, (
        f"new agent module(s) {sorted(unlisted)} are in neither THIN_AGENTS nor "
        f"LEGACY_BUDGET. Classify them: a thin agent asserts zero arithmetic, a "
        f"legacy one gets a budget that may only fall."
    )


def test_the_hardcoded_cess_rate_is_recorded_as_the_worst_offender() -> None:
    """`advanced_calculator` multiplies by a literal 0.04.

    Documented here because it is the single clearest example of why AGT-001
    matters: the cess rate lives in the rule pack, is 4% today, and an agent
    carrying its own copy is exactly how v1's seven disagreeing tax tables
    happened.
    """
    path = AGENTS / "advanced_calculator.py"
    if not path.exists():
        pytest.skip("advanced_calculator.py has been removed — AGT-001 progressed")
    assert "0.04" in path.read_text(encoding="utf-8"), (
        "the hardcoded cess has gone — update or delete this test and lower "
        "the LEGACY_BUDGET entry"
    )
