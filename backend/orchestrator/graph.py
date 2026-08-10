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
            
            # Aggregate validation reports from all agents
            all_warnings = []
            all_corrections = []
            all_sources = []
            confidence_scores = []
            
            for agent_name, agent_result in results.items():
                v_report = None
                if hasattr(agent_result, "validation_report") and agent_result.validation_report:
                    v_report = agent_result.validation_report
                elif isinstance(agent_result, dict) and "validation_report" in agent_result:
                    v_report = agent_result["validation_report"]
                
                if v_report and isinstance(v_report, dict):
                    all_warnings.extend(v_report.get("warnings", []))
                    all_corrections.extend(v_report.get("corrections_applied", []))
                    all_sources.extend(v_report.get("sources_verified", []))
                    cs = v_report.get("confidence_score")
                    if cs is not None:
                        confidence_scores.append(cs)
            
            avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.8
            
            validation_summary = {
                "sources_verified": len(all_sources),
                "total_warnings": len(all_warnings),
                "warnings": all_warnings[:10],  # Top 10
                "corrections_applied": all_corrections[:10],
                "avg_confidence": round(avg_confidence, 2),
                "agents_validated": len(confidence_scores),
            }
            
            # Return orchestration result
            return {
                "user_query": user_query,
                "agents_invoked": agents_to_invoke,
                "agent_results": results,
                "execution_log": execution_log,
                "tools_available": len(self.tools.list_tools()) if self.tools else 0,
                "validation_summary": validation_summary
            }
        
        except Exception as e:
            logger.error(f"Orchestration error: {e}")
            return {
                "error": str(e),
                "user_query": user_query,
                "agent_results": {},
                "validation_summary": {"avg_confidence": 0.0, "total_warnings": 1, "warnings": [str(e)]}
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
