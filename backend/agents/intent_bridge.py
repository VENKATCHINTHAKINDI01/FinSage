"""Intent-to-pipeline bridge — AGT-001.

Routes detected intents through the deterministic core engine and the
Analyst→Reviewer pipeline. This replaces the legacy path where each agent
carried its own slab tables and asked the LLM to compute.

The flow is:

    intent → select core computations → run them → feed results to pipeline

Every rupee figure the user sees originates from ``backend.core``. The LLM's
only job is drafting the explanation text, subject to CA and risk review.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from backend.agents import pipeline
from backend.agents.analyst import Analyst
from backend.agents.reviewer_ca import CAReviewer
from backend.agents.reviewer_risk import RiskReviewer
from backend.llm import get_llm, is_configured
from backend.tools.calculation import TaxCalculationEngine, current_fy

logger = logging.getLogger(__name__)

# Intents that the new pipeline handles. Everything else falls through to the
# legacy orchestrator until those agents are also migrated.
_PIPELINE_INTENTS = frozenset({
    "tax_deduction",
    "tax_savings",
    "tax_calculation",
    "business_expense",
    "financial_planning",
    "tax_filing",
    "tax_strategy",
    "price_intelligence",
    "wealth_planning",
    "general",
})

# ── Tool-result builders ────────────────────────────────────────────────────
# Each function runs the appropriate core engine computation and returns the
# result in the ``{tool, success, result}`` shape the Analyst expects.


def _compute_tax(ctx: dict[str, Any], fy: str) -> dict[str, Any]:
    """Basic income-tax computation via the core engine."""
    income = float(ctx.get("annual_income", 0))
    if income <= 0:
        return {"tool": "compute_tax", "success": False, "error": "no income provided"}

    age = int(ctx.get("age", 35))
    deductions = {}
    for key in ("80C", "80D", "80CCD_1B", "24b", "10_13A", "80E", "80G", "80TTA"):
        val = ctx.get(f"deduction_{key}") or ctx.get(key)
        if val:
            deductions[key] = float(val)

    result = TaxCalculationEngine.calculate_tax_with_deductions(
        gross_income=income,
        deductions=deductions or None,
        fy=fy,
        regime=ctx.get("regime", "new"),
        age=age,
        is_salary=ctx.get("employment_type", "salaried") in ("salaried", "individual"),
    )
    return {"tool": "compute_tax", "success": True, "result": result}


def _compare_regimes(ctx: dict[str, Any], fy: str) -> dict[str, Any]:
    """Old vs new regime comparison via the core engine."""
    income = float(ctx.get("annual_income", 0))
    if income <= 0:
        return {"tool": "compare_regimes", "success": False, "error": "no income provided"}

    age = int(ctx.get("age", 35))
    deductions = {}
    for key in ("80C", "80D", "80CCD_1B", "24b", "10_13A"):
        val = ctx.get(f"deduction_{key}") or ctx.get(key)
        if val:
            deductions[key] = float(val)

    result = TaxCalculationEngine.compare_regimes(
        gross_income=income,
        deductions=deductions or None,
        fy=fy,
        age=age,
    )
    return {"tool": "compare_regimes", "success": True, "result": result}


def _select_itr_form(ctx: dict[str, Any], fy: str) -> dict[str, Any]:
    """ITR form selection via the core engine."""
    try:
        result = TaxCalculationEngine.select_itr_form(
            entity_type=ctx.get("entity_type", "individual"),
            residency=ctx.get("residency", "resident"),
            has_salary=ctx.get("employment_type", "salaried") in ("salaried", "individual"),
            has_business_income=ctx.get("employment_type") in ("business", "freelance"),
            total_income=float(ctx.get("annual_income", 0)),
            fy=fy,
        )
        return {"tool": "select_itr_form", "success": True, "result": result}
    except Exception as exc:
        return {"tool": "select_itr_form", "success": False, "error": str(exc)}


# Map of intent → which core computations to run.
_INTENT_TOOLS: dict[str, list] = {
    "tax_deduction": [_compute_tax],
    "tax_savings": [_compute_tax, _compare_regimes],
    "tax_calculation": [_compute_tax],
    "business_expense": [_compute_tax],
    "financial_planning": [_compute_tax, _compare_regimes],
    "tax_filing": [_compute_tax, _select_itr_form],
    "tax_strategy": [_compute_tax, _compare_regimes],
    "price_intelligence": [_compute_tax],
    "wealth_planning": [_compute_tax],
    "general": [_compute_tax],
}


# ── Public API ──────────────────────────────────────────────────────────────


def handles_intent(intent: str) -> bool:
    """Whether this bridge handles the given intent."""
    return intent in _PIPELINE_INTENTS


async def run_for_intent(
    *,
    query: str,
    intent: str,
    user_context: dict[str, Any],
    fy: str | None = None,
) -> dict[str, Any]:
    """Run the full pipeline for an intent.

    Returns a dict compatible with the chat endpoint's expected format.
    """
    fy = fy or current_fy()
    regime = user_context.get("regime", "new")

    # 1. Run the appropriate core engine computations
    tool_fns = _INTENT_TOOLS.get(intent, [_compute_tax])
    tool_results = [fn(user_context, fy) for fn in tool_fns]

    # 2. Build profile for the Analyst
    profile = {
        "income": user_context.get("annual_income", 0),
        "employment_type": user_context.get("employment_type", "individual"),
        "age": user_context.get("age", 35),
        "user_id": user_context.get("user_id"),
    }

    # 3. Run the Analyst→Reviewer pipeline
    llm = get_llm() if is_configured() else None
    result = await pipeline.run(
        query=query,
        profile=profile,
        fy=fy,
        regime=regime,
        tool_results=tool_results,
        analyst=Analyst(llm=llm),
        reviewer=CAReviewer(),
        risk_reviewer=RiskReviewer(),
    )

    # 4. Format as the chat endpoint expects
    answer = result.answer
    return {
        "user_query": query,
        "intent": intent,
        "pipeline": True,
        "agents_invoked": ["analyst", "reviewer_ca", "reviewer_risk"],
        "agent_results": {
            "pipeline": {
                "result": {
                    "answer": answer.text,
                    "reviewed": True,
                    "withheld": answer.withheld,
                    "redrafted": answer.redrafted,
                    "caveats": answer.caveats,
                },
                "confidence": 0.0 if answer.withheld else 0.9,
                "status": "withheld" if answer.withheld else "success",
            },
        },
        "execution_log": [
            {
                "agent": "pipeline",
                "status": "withheld" if answer.withheld else "success",
                "time_ms": result.total_latency_ms,
                "llm_calls": result.llm_calls,
            },
        ],
        "review_summary": pipeline.summarise_for_evidence_pack(result),
        "validation_summary": {
            "sources_verified": len(tool_results),
            "total_warnings": 0,
            "warnings": [],
            "avg_confidence": 0.0 if answer.withheld else 0.9,
            "agents_validated": 1,
        },
    }
