from backend.orchestrator.agent_state import AgentState
from backend.orchestrator.intent_detector import detect_intent

async def intent_router(state: AgentState) -> str:
    """Decide which node to execute next based on remaining agents."""
    agents = state.get("agents_to_invoke", [])
    
    # If no intent has been mapped or agents specified, run intent detector
    if not state.get("intent") or not agents:
        intent_res = await detect_intent(state["user_query"], state["user_id"])
        state["intent"] = intent_res.intent.value
        state["agents_to_invoke"] = intent_res.agents_to_invoke
        agents = intent_res.agents_to_invoke

    # Route sequentially: income_classifier -> deduction_hunter -> tax_optimizer
    if "income_classifier_agent" in agents and "income_classifier_agent" not in state.get("agent_results", {}):
        return "income_classifier"
    elif "deduction_hunter_agent" in agents and "deduction_hunter_agent" not in state.get("agent_results", {}):
        return "deduction_hunter"
    elif "tax_optimizer_agent" in agents and "tax_optimizer_agent" not in state.get("agent_results", {}):
        return "tax_optimizer"
    
    return "generate_response"

def should_run_income_classifier(state: AgentState) -> bool:
    """Helper condition to check if income classifier agent is in list."""
    return "income_classifier_agent" in state.get("agents_to_invoke", [])
