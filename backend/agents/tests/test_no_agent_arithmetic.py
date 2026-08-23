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
    # AGT-001 (2026-08-23): reached zero, so promoted out of LEGACY_BUDGET —
    # the ratchet is only meaningful if a module that gets fixed graduates to
    # the no-tolerance list rather than sitting on a budget of 0.
    #
    # tax_strategy: the 3-year projection subtracted a HARDCODED standard
    # deduction (₹50,000 old / ₹75,000 new, under a comment reading
    # "FY 24-25") and then compared the regimes by hand. Those figures are
    # still correct for FY 2026-27, which made this worse than a wrong value:
    # right by coincidence, and silently stale the first time a Finance Act
    # moves either one. Now uses TaxCalculationEngine.compare_regimes.
    "tax_strategy.py",
    # tax_agent: `total_deduction * tax_bracket` against a private slab table
    # whose first threshold was ₹2,50,000 — the OLD regime's basic exemption
    # applied to everyone, when the new regime's is ₹4,00,000 and the new
    # regime is the default. It was the SIXTH private copy of the slab table
    # in this codebase. Now uses calculate_deduction_benefit, which recomputes
    # the tax both ways rather than multiplying by a marginal rate.
    "tax_agent.py",
    # cross_border_tax: quoted a specific rupee Foreign Tax Credit
    # entitlement "under Section 90/91", derived from
    # `indian_tax_rate = 0.30 # assumed marginal bracket`. Rule 128 computes
    # the credit per country and per head of income against the taxpayer's
    # whole Indian position, so a single flat-rate figure can be wrong even
    # with the right rate. States the test and Form 67 now; the amount is
    # None, and None is not 0.0 — zero would be the claim "you are entitled
    # to nothing", which this agent is not in a position to make.
    "cross_border_tax.py",
}

# v1 modules awaiting the AGT-001 rewrite, with today's count. RATCHET: these
# may only go down. Lower a number when you fix a module; never raise one.
LEGACY_BUDGET = {
    # AGT-001 (2026-08-19): 24 -> 18. The slab/rebate/surcharge/cess
    # computation itself now goes through TaxCalculationEngine.calculate_tax_full
    # (backend.core) instead of a duplicate hardcoded slab table with no 87A
    # rebate at all. What remains is raw income summation, refund/balance
    # subtraction, and the equity capital-gains flat-rate multiplication
    # (whose RATE is sourced from TaxCalculationEngine.equity_capital_gains_rates,
    # but the multiplication itself still trips the arithmetic scanner) —
    # not tax knowledge invented in the agent.
    "advanced_calculator.py": 18,
    "tools.py": 13,
    # AGT-001 (2026-08-23): 6 -> 5. The removed site was
    # `calculated_tax = ... or annual_income * 0.20`, an invented flat rate
    # standing in for the user's real tax and used to decide whether to RAISE
    # A RED FLAG. A salaried user on ₹6,00,000 with correctly deducted nil TDS
    # was compared against a fabricated ₹1,20,000 and warned of a "TDS vs 26AS
    # mismatch" that did not exist. The five that remain are threshold
    # heuristics — a 5% deductions-to-income ratio, a 15% TDS tolerance, a 10%
    # Form-16 tolerance — which decide whether to LOOK at something, and are
    # not figures presented to anyone as tax.
    "compliance_checker.py": 5,
    "income_classifier.py": 6,
    # AGT-001 (2026-08-23): 6 -> 2. Removed `annual_income * 0.20` as the
    # user's estimated tax and the advance-tax instalments at 25/50/75, which
    # are not the statutory percentages — s.211 of the 1961 Act and s.404 of
    # the 2025 Act both say 15/45/75/100. Both now come from
    # TaxCalculationEngine, which reads the schedule from the rule pack.
    #
    # The 2 remaining are FALSE POSITIVES: `base_requirements["documents"] +
    # [...]`, list concatenation whose source text happens to mention a money
    # word. Left in the budget rather than fixed by loosening the detector —
    # the detector over-reports on purpose (see `money_arithmetic_sites`), and
    # a guard tuned to make a number look good is not a guard.
    "itr_helper.py": 2,
    "deduction_hunter.py": 2,
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


# `test_the_hardcoded_cess_rate_is_recorded_as_the_worst_offender` — removed
# 2026-08-19. It asserted `advanced_calculator.py` still carried its own
# literal `0.04` cess multiplier, as the clearest example of why AGT-001
# matters. AGT-001 fixed exactly that: cess now comes from
# `TaxCalculationEngine.calculate_tax_full` (backend.core), alongside the
# rest of that module's slab/rebate/surcharge computation. The
# LEGACY_BUDGET entry above was lowered in the same change.
