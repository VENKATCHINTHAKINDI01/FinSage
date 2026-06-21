"""
Chat endpoint - HTTP POST /api/v1/chat/query
User sends query, gets full response synchronously.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, Optional
from pydantic import BaseModel
import logging

from backend.db.postgres import get_session
from backend.security.dependencies import get_current_user
from backend.orchestrator.memory import get_or_create_memory
from backend.orchestrator import AdvancedAgentOrchestrator, run_workflow
from backend.tools import ToolExecutor

from backend.agents.income_classifier import IncomeClassifierAgent
from backend.agents.deduction_hunter import DeductionHunterAgent
from backend.agents.tax_optimizer import TaxOptimizerAgent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

# Global intent detector
intent_detector = None


class OrchestratorProxy:
    def __getattr__(self, name):
        from backend.orchestrator.graph import get_orchestrator
        orch = get_orchestrator()
        if orch is None:
            raise RuntimeError("Orchestrator not initialized")
        return getattr(orch, name)
        
    def __setattr__(self, name, value):
        from backend.orchestrator.graph import get_orchestrator
        orch = get_orchestrator()
        if orch is None:
            raise RuntimeError("Orchestrator not initialized")
        setattr(orch, name, value)


orchestrator = OrchestratorProxy()


class ChatQueryRequest(BaseModel):
    query: str
    conversation_id: Optional[str] = None


def get_db():
    """Placeholder get_db function for startup events."""
    return None


@router.on_event("startup")
async def startup_event():
    """Initialize on app startup."""
    logger.info("🚀 Starting FinSage AI")
    
    # Get tools from main
    from backend.main import tool_executor
    
    # Initialize intent detector
    global intent_detector
    intent_detector = IntentDetector()
    
    # Initialize orchestrator with tools
    from backend.orchestrator.graph import init_orchestrator
    await init_orchestrator(tools=tool_executor)
    
    # Register agents
    from backend.agents.income_classifier import IncomeClassifierAgent
    from backend.agents.deduction_hunter import DeductionHunterAgent
    from backend.agents.tax_optimizer import TaxOptimizerAgent
    
    orchestrator.register_agent(
        "income_classifier_agent",
        IncomeClassifierAgent()
    )
    orchestrator.register_agent(
        "deduction_hunter_agent",
        DeductionHunterAgent()
    )
    orchestrator.register_agent(
        "tax_optimizer_agent",
        TaxOptimizerAgent()
    )
    from backend.agents.benefits_discovery import BenefitsDiscoveryAgent
    orchestrator.register_agent(
        "benefits_discovery_agent",
        BenefitsDiscoveryAgent()
    )
    from backend.agents.eligibility_verifier import EligibilityVerifierAgent
    orchestrator.register_agent(
        "eligibility_verifier_agent",
        EligibilityVerifierAgent()
    )
    from backend.agents.compliance_checker import ComplianceCheckerAgent
    orchestrator.register_agent(
        "compliance_checker_agent",
        ComplianceCheckerAgent()
    )
    from backend.agents.itr_helper import ITRHelperAgent
    orchestrator.register_agent(
        "itr_helper_agent",
        ITRHelperAgent()
    )
    from backend.agents.advanced_calculator import AdvancedCalculatorAgent
    orchestrator.register_agent(
        "advanced_calculator_agent",
        AdvancedCalculatorAgent()
    )
    from backend.agents.cross_border_tax import CrossBorderTaxAgent
    orchestrator.register_agent(
        "cross_border_tax_agent",
        CrossBorderTaxAgent()
    )
    from backend.agents.price_intelligence import PriceIntelligenceAgent
    orchestrator.register_agent(
        "price_intelligence_agent",
        PriceIntelligenceAgent()
    )
    from backend.agents.tax_strategy import TaxStrategyAgent
    orchestrator.register_agent(
        "tax_strategy_agent",
        TaxStrategyAgent()
    )
    from backend.agents.wealth_planner import WealthPlannerAgent
    orchestrator.register_agent(
        "wealth_planner_agent",
        WealthPlannerAgent()
    )

    
    logger.info(f"✅ Ready: {len(orchestrator.agents)} agents, {len(tool_executor.list_tools()) if tool_executor else 0} tools")


async def get_user_context(user_id: str, session: AsyncSession) -> Dict[str, Any]:
    """Helper to fetch user financial profile and build query context."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from backend.db.orm_models import User
    
    try:
        result = await session.execute(
            select(User)
            .options(selectinload(User.financial_profile))
            .where(User.id == user_id)
        )
        user_obj = result.scalar_one_or_none()
        
        user_context = {
            "user_id": user_id,
            "email": user_obj.email if user_obj else "",
            "full_name": user_obj.full_name if user_obj else "",
            "annual_income": 0,
            "employment_type": "individual",
        }
        
        if user_obj and user_obj.financial_profile:
            user_context["annual_income"] = float(user_obj.financial_profile.annual_income)
            user_context["employment_type"] = user_obj.financial_profile.employment_type
            
        return user_context
    except Exception as e:
        logger.error(f"Error fetching user context: {e}")
        return {
            "user_id": user_id,
            "email": "",
            "full_name": "",
            "annual_income": 0,
            "employment_type": "individual",
        }


@router.post("/query")
async def chat_query(
    request: ChatQueryRequest,
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """
    Process chat query with tools-enabled agents.
    
    Flow:
      1. Detect intent
      2. Get agents for intent
      3. Run orchestrator (agents use tools)
      4. Return results
    """
    from backend.orchestrator.graph import db_session_var, get_orchestrator
    token = db_session_var.set(session)
    
    try:
        logger.info(f"Chat query from user {current_user.id}")
        
        # Get orchestrator
        orch = get_orchestrator()
        if not orch:
            raise HTTPException(status_code=503, detail="System not initialized")
        
        # Get user context
        context_data = await get_user_context(current_user.id, session)
        
        # Detect intent
        intent_result = await intent_detector.detect_intent(request.query)
        intent = intent_result.intent.value if hasattr(intent_result, 'intent') else "general"
        agents_to_invoke = intent_result.agents_to_invoke if hasattr(intent_result, 'agents_to_invoke') else None
        
        user_context = {
            "user_id": current_user.id,
            "email": current_user.email,
            "annual_income": context_data.get("annual_income", 0.0),
            "employment_type": context_data.get("employment_type", "individual"),
            "age": getattr(current_user, 'age', 35),
            **context_data
        }
        
        # Run orchestration (agents use tools!)
        result = await orch.orchestrate(
            user_query=request.query,
            user_id=current_user.id,
            user_context=user_context,
            intent=intent,
            agents_to_invoke=agents_to_invoke,
            conversation_id=request.conversation_id
        )
        
        # Process agent results
        agent_responses = {}
        total_savings = 0
        quality_scores = []
        
        for agent_name, agent_result in result.get("agent_results", {}).items():
            res_dict = {}
            confidence = 0.0
            
            if hasattr(agent_result, "result"):
                res_dict = agent_result.result
                confidence = agent_result.confidence
            elif isinstance(agent_result, dict):
                res_dict = agent_result.get("result", {})
                confidence = agent_result.get("confidence", 0.0)
            else:
                continue
                
            agent_responses[agent_name] = res_dict
            
            # Track savings
            if "total_estimated_savings" in res_dict:
                total_savings += res_dict["total_estimated_savings"]
            elif "total_tax_savings" in res_dict:
                total_savings += res_dict["total_tax_savings"]
            elif "total_potential_savings" in res_dict:
                total_savings += res_dict["total_potential_savings"]
            
            # Track quality
            quality_scores.append(confidence)
        
        # Calculate average quality
        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0
        
        # Get or create memory
        memory = get_or_create_memory(current_user.id)
        
        # Add to conversation memory
        await memory["conversation"].add_turn(
            query=request.query,
            agent_responses=agent_responses,
            total_savings=total_savings
        )
        
        # Learn from response
        if "income_classifier_agent" in agent_responses:
            income = agent_responses["income_classifier_agent"].get("income_sources", [])
            for source in income:
                await memory["semantic"].learn_income_source(
                    source.get("type", "unknown"),
                    source.get("amount", 0)
                )
        
        if "deduction_hunter_agent" in agent_responses:
            deductions = agent_responses["deduction_hunter_agent"].get("deductions_found", [])
            for ded in deductions:
                await memory["semantic"].learn_deduction(
                    ded.get("category", "unknown"),
                    ded.get("amount", 0)
                )
        
        # Get conversation context
        conv_context = memory["conversation"].get_context()
        known_deductions = memory["semantic"].get_known_deductions()
        
        return {
            "success": True,
            "query": request.query,
            "intent": intent,
            "agent_responses": agent_responses,
            "total_estimated_savings": total_savings,
            "quality_score": int(avg_quality * 100),
            "execution_log": result.get("execution_log", []),
            "agents_executed": len(result.get("agent_results", {})),
            "tools_available": result.get("tools_available", 0),
            "conversation_history_length": len(memory["conversation"].turns),
            "known_deductions": known_deductions
        }
    
    except Exception as e:
        logger.error(f"Chat query error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db_session_var.reset(token)


@router.get("/health")
async def chat_health():
    """Check if chat service is healthy."""
    from backend.orchestrator.graph import get_orchestrator
    orch = get_orchestrator()
    return {
        "status": "ok",
        "service": "chat",
        "agents_registered": len(orch.agents) if orch else 0
    }


@router.get("/tools")
async def get_tools():
    """Get available tools."""
    from backend.orchestrator.graph import get_orchestrator
    orch = get_orchestrator()
    if not orch or not orch.tools:
        return {"tools_available": 0, "tools": []}
    
    return {
        "tools_available": len(orch.tools.list_tools()),
        "tools_by_category": orch.tools.get_tool_categories(),
        "total_agents": len(orch.agents)
    }