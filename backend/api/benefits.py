from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Dict, Any, List, Optional

from backend.services.user_context import fetch_user_context
from backend.db.postgres import get_session
from backend.security.dependencies import get_current_user
from backend.orchestrator.graph import get_orchestrator, db_session_var

router = APIRouter(prefix="/api/v1/benefits", tags=["benefits"])


class BenefitsQueryRequest(BaseModel):
    """Query for benefits discovery."""
    query: Optional[str] = "What government schemes am I eligible for?"
    conversation_id: Optional[str] = None


class EligibilityCheckRequest(BaseModel):
    """Check eligibility for specific scheme."""
    scheme_code: str
    conversation_id: Optional[str] = None


@router.post("/discover")
async def discover_benefits(
    request: BenefitsQueryRequest,
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """
    Discover government schemes user qualifies for.
    
    • Analyzes profile
    • Finds applicable schemes
    • Returns benefits + savings
    """
    
    orchestrator = get_orchestrator()
    if not orchestrator:
        raise HTTPException(status_code=503, detail="System not ready")
        
    token = db_session_var.set(session)
    
    try:
        # Was getattr(current_user, "age", 35) etc. — current_user is the
        # bare auth/User record (email, name, password hash), which has
        # none of these attributes, so every field silently fell back to
        # its default on every single call: age 35, salaried, ₹0 income,
        # no health insurance, for every user regardless of their real
        # profile. fetch_user_context reads the actual saved profile_data,
        # same as the /calculator and /suggestions endpoints.
        user_context = await fetch_user_context(current_user.id, current_user.email, session)

        # Run orchestration
        result = await orchestrator.orchestrate(
            user_query=request.query or "What government schemes am I eligible for?",
            user_id=current_user.id,
            user_context=user_context,
            agents_to_invoke=["benefits_discovery_agent"],
            conversation_id=request.conversation_id
        )
        
        # Process result
        agent_result = result.get("agent_results", {}).get("benefits_discovery_agent", {})
        
        # In case the result is an AgentOutput object
        res_data = {}
        if hasattr(agent_result, "result"):
            res_data = agent_result.result
        elif isinstance(agent_result, dict):
            res_data = agent_result.get("result", {})
            
        return {
            "success": True,
            "schemes_found": res_data.get("schemes_found", 0),
            "scheme_details": res_data.get("scheme_details", []),
            "categories": res_data.get("categories", {}),
            "top_recommendations": res_data.get("top_recommendations", []),
            "total_potential_savings": res_data.get("total_potential_savings", 0),
            "action_items": res_data.get("action_items", [])
        }
    
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in discover_benefits: {e}", exc_info=True)
        raise  # DEM-008: handled globally; str(e) must not reach the client
    finally:
        db_session_var.reset(token)


@router.post("/verify-eligibility")
async def verify_eligibility(
    request: EligibilityCheckRequest,
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """
    Verify eligibility for specific scheme.
    
    • Checks all criteria
    • Identifies missing docs
    • Provides guidance
    • Suggests alternatives
    """
    
    orchestrator = get_orchestrator()
    if not orchestrator:
        raise HTTPException(status_code=503, detail="System not ready")
        
    token = db_session_var.set(session)
    
    try:
        # Same fix as discover_benefits above — current_user has none of
        # these attributes, so every check ran against a fabricated
        # age-35/salaried/₹0-income/no-insurance profile regardless of who
        # was actually asking.
        user_context = await fetch_user_context(current_user.id, current_user.email, session)

        # Run orchestration
        query = f"Am I eligible for scheme {request.scheme_code}?"
        
        result = await orchestrator.orchestrate(
            user_query=query,
            user_id=current_user.id,
            user_context=user_context,
            agents_to_invoke=["eligibility_verifier_agent"],
            conversation_id=request.conversation_id
        )
        
        # Process result
        agent_result = result.get("agent_results", {}).get("eligibility_verifier_agent", {})
        
        # In case the result is an AgentOutput object
        res_data = {}
        if hasattr(agent_result, "result"):
            res_data = agent_result.result
        elif isinstance(agent_result, dict):
            res_data = agent_result.get("result", {})
            
        return {
            "success": True,
            "scheme_code": request.scheme_code,
            "eligible": res_data.get("eligible", False),
            "status": res_data.get("status", "Unknown"),
            "reasons": res_data.get("reasons", []),
            "documents_required": res_data.get("documents_required", []),
            "alternatives": res_data.get("alternative_schemes", []),
            "next_steps": res_data.get("next_steps", [])
        }
    
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in verify_eligibility: {e}", exc_info=True)
        raise  # DEM-008: handled globally; str(e) must not reach the client
    finally:
        db_session_var.reset(token)


@router.get("/schemes")
async def list_all_schemes(
    current_user = Depends(get_current_user)
):
    """
    List all available government schemes.

    • 9 major tax schemes
    • Descriptions + limits
    • Eligibility summary
    """
    # Was its own separate hardcoded list — a THIRD independent copy of the
    # same 80D/80CCD-limit bug already fixed in tools/schemes_search.py's
    # GovernmentSchemesDatabase.SCHEMES (150000 for both, one of them 80C's
    # limit copy-pasted). Deriving from that single corrected source instead
    # of maintaining a second one that can drift out of sync with it again.
    from backend.tools.schemes_search import GovernmentSchemesDatabase

    schemes_list = [
        {
            "code": code,
            "name": details["name"],
            "limit": details["limit"],
            "category": details["category"],
        }
        for code, details in GovernmentSchemesDatabase.SCHEMES.items()
    ]

    return {
        "success": True,
        "total_schemes": len(schemes_list),
        "schemes": schemes_list
    }
