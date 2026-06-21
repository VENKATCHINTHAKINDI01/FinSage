import logging
from typing import Any, Dict
from backend.orchestrator.agent_state import AgentState

logger = logging.getLogger(__name__)

# Registry to store orchestrator instance at runtime and avoid circular imports
_orchestrator = None

def set_orchestrator(orchestrator_instance):
    """Set the global orchestrator instance for execution nodes."""
    global _orchestrator
    _orchestrator = orchestrator_instance

async def income_classifier_node(state: AgentState) -> AgentState:
    """Execute the Income Classifier agent and update state."""
    logger.info("Executing income_classifier_node")
    if not _orchestrator:
        logger.error("Orchestrator instance not set in execution_nodes")
        return state
        
    agent = _orchestrator.agents.get("income_classifier_agent") or _orchestrator.agents.get("income_classifier")
    if not agent:
        logger.warning("Income Classifier Agent not found")
        return state
        
    try:
        # Run agent
        result = await agent.execute(
            user_query=state["user_query"],
            user_context=state["user_context"],
            tools=_orchestrator.tools
        )
        
        # Save results in state
        state["agent_results"]["income_classifier_agent"] = result
        if result.status == "success" and isinstance(result.result, dict):
            state["income_analysis"] = result.result
            
            # Propagate income info into user_context for subsequent agents
            total_income = result.result.get("total_income", 0.0)
            if total_income > 0:
                state["user_context"]["annual_income"] = total_income
            state["user_context"]["income_sources"] = result.result.get("income_sources", [])
            
    except Exception as e:
        logger.error(f"Error in income_classifier_node: {e}", exc_info=True)
        state["error"] = str(e)
        
    return state

async def deduction_hunter_node(state: AgentState) -> AgentState:
    """Execute the Deduction Hunter agent and update state."""
    logger.info("Executing deduction_hunter_node")
    if not _orchestrator:
        logger.error("Orchestrator instance not set in execution_nodes")
        return state
        
    agent = _orchestrator.agents.get("deduction_hunter_agent") or _orchestrator.agents.get("deduction_hunter")
    if not agent:
        logger.warning("Deduction Hunter Agent not found")
        return state
        
    try:
        # Update user_context with previous step results if needed
        context = {**state["user_context"]}
        if state["income_analysis"]:
            context["income_analysis"] = state["income_analysis"]
            
        # Run agent
        result = await agent.execute(
            user_query=state["user_query"],
            user_context=context,
            tools=_orchestrator.tools
        )
        
        # Save results in state
        state["agent_results"]["deduction_hunter_agent"] = result
        if result.status == "success" and isinstance(result.result, dict):
            state["deductions_found"] = result.result.get("deductions", [])
            
            # Propagate deductions into user_context for the next agent
            state["user_context"]["deductions"] = state["deductions_found"]
            state["user_context"]["total_deduction_amount"] = sum(
                float(d.get("amount", 0.0)) for d in state["deductions_found"]
            )
            
    except Exception as e:
        logger.error(f"Error in deduction_hunter_node: {e}", exc_info=True)
        state["error"] = str(e)
        
    return state

async def tax_optimizer_node(state: AgentState) -> AgentState:
    """Execute the Tax Optimizer agent and update state."""
    logger.info("Executing tax_optimizer_node")
    if not _orchestrator:
        logger.error("Orchestrator instance not set in execution_nodes")
        return state
        
    agent = _orchestrator.agents.get("tax_optimizer_agent") or _orchestrator.agents.get("tax_optimizer")
    if not agent:
        logger.warning("Tax Optimizer Agent not found")
        return state
        
    try:
        # Merge all context so far
        context = {
            **state["user_context"],
            "income_analysis": state["income_analysis"],
            "deductions_found": state["deductions_found"]
        }
        
        # Run agent
        result = await agent.execute(
            user_query=state["user_query"],
            user_context=context,
            tools=_orchestrator.tools
        )
        
        # Save results in state
        state["agent_results"]["tax_optimizer_agent"] = result
        if result.status == "success" and isinstance(result.result, dict):
            state["strategies_validated"] = result.result.get("strategies", [])
            state["savings"] = result.result.get("estimated_annual_savings", 0.0)
            
    except Exception as e:
        logger.error(f"Error in tax_optimizer_node: {e}", exc_info=True)
        state["error"] = str(e)
        
    return state
