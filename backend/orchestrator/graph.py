"""
Agent Orchestrator - Multi-Agent Coordinator
============================================

Routes queries to agents and manages execution.
"""

import logging
import contextvars
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Request-scoped database session ContextVar
db_session_var = contextvars.ContextVar("db_session", default=None)


class AsyncSessionProxy:
    """Proxy for accessing the active request-scoped database session."""
    
    def __getattr__(self, name):
        session = db_session_var.get()
        if session is None:
            raise RuntimeError("No active database session in this context")
        return getattr(session, name)


class AgentOrchestrator:
    """
    Routes queries to agents.
    Passes tools to agents.
    Manages execution.
    """
    
    def __init__(self, tools=None):
        """Initialize orchestrator with tools."""
        self.agents = {}
        self.tools = tools
        logger.info("Orchestrator initialized")
    
    def register_agent(self, name: str, agent):
        """Register an agent and inject tools."""
        # Inject tools
        if self.tools:
            agent.set_tools(self.tools)
        
        self.agents[name] = agent
        logger.info(f"Registered agent: {name}")
        return self
    
    async def orchestrate(
        self,
        user_query: str,
        user_id: str,
        user_context: Dict[str, Any],
        intent: str = "general",
        agents_to_invoke: Optional[List[str]] = None,
        conversation_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Orchestrate agent execution.
        
        • Determine agents to run
        • Execute sequentially
        • Combine results
        • Return response
        """
        logger.info(f"Orchestrating for user {user_id}")
        
        try:
            # Get agents to invoke
            if not agents_to_invoke:
                agents_to_invoke = list(self.agents.keys())
            
            logger.info(f"Invoking agents: {', '.join(agents_to_invoke)}")
            
            # Execute agents
            results = {}
            execution_log = []
            
            for agent_name in agents_to_invoke:
                if agent_name not in self.agents:
                    logger.warning(f"Agent {agent_name} not found")
                    continue
                
                agent = self.agents[agent_name]
                
                try:
                    logger.info(f"Executing {agent_name}")
                    
                    # Execute agent with tools
                    result = await agent.execute(
                        user_query=user_query,
                        user_context=user_context,
                        tools=self.tools
                    )
                    
                    results[agent_name] = result
                    
                    # Handle both AgentOutput objects and raw dictionaries
                    status = result.status if hasattr(result, "status") else result.get("status", "success")
                    time_ms = result.execution_time_ms if hasattr(result, "execution_time_ms") else result.get("execution_time_ms", 0)
                    confidence = result.confidence if hasattr(result, "confidence") else result.get("confidence", 0.0)
                    
                    execution_log.append({
                        "agent": agent_name,
                        "status": status,
                        "time_ms": time_ms,
                        "confidence": confidence
                    })
                    
                    logger.info(f"{agent_name} completed: {status}")
                
                except Exception as e:
                    logger.error(f"Agent {agent_name} error: {e}", exc_info=True)
                    execution_log.append({
                        "agent": agent_name,
                        "status": "error",
                        "error": str(e)
                    })
                    results[agent_name] = {
                        "status": "error",
                        "error": str(e)
                    }
            
            # Return orchestration result
            return {
                "user_query": user_query,
                "agents_invoked": agents_to_invoke,
                "agent_results": results,
                "execution_log": execution_log,
                "tools_available": len(self.tools.list_tools()) if self.tools else 0
            }
        
        except Exception as e:
            logger.error(f"Orchestration error: {e}")
            return {
                "error": str(e),
                "user_query": user_query,
                "agent_results": {}
            }


# Global orchestrator instance
orchestrator: Optional[AgentOrchestrator] = AgentOrchestrator()


async def init_orchestrator(tools=None):
    """Initialize orchestrator with tools."""
    global orchestrator
    if orchestrator is None:
        orchestrator = AgentOrchestrator(tools=tools)
    else:
        orchestrator.tools = tools
        # Re-inject tools into already registered agents
        if tools:
            for agent in orchestrator.agents.values():
                agent.set_tools(tools)
    return orchestrator


def get_orchestrator() -> Optional[AgentOrchestrator]:
    """Get orchestrator instance."""
    return orchestrator
