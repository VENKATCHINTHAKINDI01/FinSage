import logging
from typing import Dict, Any, Optional
from langgraph.graph import StateGraph, END

from backend.orchestrator.agent_state import AgentState, create_initial_state
from backend.orchestrator.router_nodes import intent_router
from backend.orchestrator.execution_nodes import (
    income_classifier_node,
    deduction_hunter_node,
    tax_optimizer_node,
    set_orchestrator
)
from backend.orchestrator.response_generation import generate_response

logger = logging.getLogger(__name__)

class AdvancedAgentOrchestrator:
    def __init__(self, agents: Optional[Dict[str, Any]] = None, tools: Optional[Any] = None):
        self.agents = agents or {}
        self.tools = tools
        
        # Register this instance in execution nodes to avoid circular imports
        set_orchestrator(self)
        
        # Compile the LangGraph workflow
        self.graph = self._build_graph()
        logger.info("AdvancedAgentOrchestrator initialized with compiled LangGraph workflow")
        
    def register_agent(self, agent_name: str, agent: Any):
        self.agents[agent_name] = agent
        logger.info(f"AdvancedAgentOrchestrator registered agent: {agent_name}")
        
    def _build_graph(self) -> StateGraph:
        # Define state graph
        workflow = StateGraph(AgentState)
        
        # Add execution nodes
        workflow.add_node("income_classifier", income_classifier_node)
        workflow.add_node("deduction_hunter", deduction_hunter_node)
        workflow.add_node("tax_optimizer", tax_optimizer_node)
        workflow.add_node("generate_response", generate_response)
        
        # Define intent-based conditional routing from startup and post-node runs
        # intent_router decides which node is next
        router_branches = {
            "income_classifier": "income_classifier",
            "deduction_hunter": "deduction_hunter",
            "tax_optimizer": "tax_optimizer",
            "generate_response": "generate_response"
        }
        
        workflow.set_conditional_entry_point(
            intent_router,
            path_map=router_branches
        )
        
        workflow.add_conditional_edges(
            "income_classifier",
            intent_router,
            path_map=router_branches
        )
        
        workflow.add_conditional_edges(
            "deduction_hunter",
            intent_router,
            path_map=router_branches
        )
        
        workflow.add_conditional_edges(
            "tax_optimizer",
            intent_router,
            path_map=router_branches
        )
        
        # Once response is compiled, terminate workflow
        workflow.add_edge("generate_response", END)
        
        return workflow.compile()

class LangGraphBuilder:
    pass

async def run_workflow(
    user_query: str,
    user_id: str,
    user_context: Dict[str, Any],
    orchestrator: AdvancedAgentOrchestrator,
    conversation_id: str = None
) -> Dict[str, Any]:
    logger.info(f"Starting advanced LangGraph workflow for user_id: {user_id}")
    
    # Initialize the state graph inputs
    initial_state = create_initial_state(
        user_query=user_query,
        user_id=user_id,
        user_context=user_context,
        conversation_id=conversation_id
    )
    
    try:
        # Run workflow via LangGraph engine
        final_state = await orchestrator.graph.ainvoke(initial_state)
        
        logger.info(f"Workflow completed successfully. Quality score: {final_state.get('quality_score')}")
        return {
            "response": final_state.get("response", ""),
            "recommendations": final_state.get("recommendations", []),
            "quality_score": final_state.get("quality_score", 0.0),
            "savings": final_state.get("savings", 0.0)
        }
    except Exception as e:
        logger.error(f"Error executing LangGraph workflow: {e}", exc_info=True)
        return {
            "response": f"An error occurred while processing your query: {str(e)}",
            "recommendations": [],
            "quality_score": 0.0,
            "savings": 0.0
        }
