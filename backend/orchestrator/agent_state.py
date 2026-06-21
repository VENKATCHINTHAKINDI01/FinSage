from typing import Dict, Any, List, TypedDict
from backend.agents.base_agent import AgentOutput

class AgentState(TypedDict):
    # Inputs
    user_query: str
    user_id: str
    user_context: Dict[str, Any]
    conversation_id: str
    
    # Routing / Orchestration
    intent: str
    agents_to_invoke: List[str]
    agent_results: Dict[str, Any]
    error: str | None
    
    # State accumulated between agent runs
    income_analysis: Dict[str, Any]
    deductions_found: List[Dict[str, Any]]
    strategies_validated: List[Dict[str, Any]]
    
    # Outputs
    response: str
    recommendations: List[str]
    quality_score: float
    savings: float

def create_initial_state(user_query: str, user_id: str, user_context: Dict[str, Any], conversation_id: str = None) -> AgentState:
    import uuid
    return {
        "user_query": user_query,
        "user_id": user_id,
        "user_context": user_context or {},
        "conversation_id": conversation_id or str(uuid.uuid4()),
        
        "intent": "",
        "agents_to_invoke": [],
        "agent_results": {},
        "error": None,
        
        "income_analysis": {},
        "deductions_found": [],
        "strategies_validated": [],
        
        "response": "",
        "recommendations": [],
        "quality_score": 0.0,
        "savings": 0.0
    }
