"""
Suggestions API — the real recommendation engine, not the fixed catalog.

Until now, nothing in the UI called tax_optimizer_agent directly. It was
only reachable through /chat/query's intent classifier, and the only chat
surface anywhere in the app (PurchaseAdvisorChat) is scoped to "should I
buy this" conversations — so Dashboard's "Top opportunities" panel fell
back to advanced_calculator_agent's optimization_suggestions: a fixed set
of exactly five possible strategies (80C, 80D, NPS, education loan, loss
carry-forward), each priced correctly but never actually reasoning about
the user's situation the way tax_optimizer_agent is built to.

tax_optimizer_agent generates candidate strategies with an LLM from the
user's real profile, cross-checks each against real scheme-eligibility
rules, prices it from the scheme's actual statutory limit (never a figure
the model guessed), and layers in the alert engine and upcoming deadlines.
This endpoint is the missing wire between that agent and the product.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.compliance import fetch_user_context
from backend.db.postgres import get_session
from backend.orchestrator.graph import db_session_var, get_orchestrator
from backend.security.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/suggestions", tags=["suggestions"])


@router.post("")
async def get_suggestions(
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Personalized tax optimization strategies for the current user.

    Returns:
    • strategies — each with a real, tool-priced savings figure or an
      explicit null (never a guess) when no statutory limit applies
    • total_estimated_savings — sum of only the priced strategies
    • savings_not_yet_determinable — names of the unpriced ones
    • implementation_timeline, upcoming_tax_deadlines, risks_and_considerations
    """
    orchestrator = get_orchestrator()
    if not orchestrator:
        raise HTTPException(status_code=503, detail="System not ready")

    token = db_session_var.set(session)

    try:
        user_context = await fetch_user_context(current_user.id, current_user.email, session)

        result = await orchestrator.orchestrate(
            user_query="What tax optimization strategies apply to my current financial situation?",
            user_id=current_user.id,
            user_context=user_context,
            agents_to_invoke=["tax_optimizer_agent"],
            # The default 20s (orchestrator/parallel.py's DEFAULT_TIMEOUT_S)
            # is calibrated for the deterministic agents — this one does an
            # LLM call to generate candidates, then per-strategy eligibility/
            # pricing tool calls, and was observed timing out in practice.
            # The per-strategy loop is now parallelized (see
            # tax_optimizer.py), which is the actual fix; this is the safety
            # margin on top of that, not a substitute for it.
            timeout_s=45.0,
        )

        agent_result = result.get("agent_results", {}).get("tax_optimizer_agent", {})

        res_data = {}
        if hasattr(agent_result, "result"):
            res_data = agent_result.result
        elif isinstance(agent_result, dict):
            res_data = agent_result.get("result", {})

        return {
            "success": True,
            "strategies": res_data.get("strategies", []),
            "total_estimated_savings": res_data.get("total_estimated_savings"),
            "savings_not_yet_determinable": res_data.get("savings_not_yet_determinable", []),
            "implementation_timeline": res_data.get("implementation_timeline"),
            "upcoming_tax_deadlines": res_data.get("upcoming_tax_deadlines", []),
            "risks_and_considerations": res_data.get("risks_and_considerations", []),
        }

    except Exception:
        raise  # DEM-008: handled globally; str(e) must not reach the client
    finally:
        db_session_var.reset(token)
