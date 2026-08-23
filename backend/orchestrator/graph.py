"""
Agent Orchestrator - Multi-Agent Coordinator
============================================

Routes queries to agents and manages execution.
"""

import contextvars
import logging
from functools import partial
from typing import Any

from backend.orchestrator.parallel import fan_out

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
        user_context: dict[str, Any],
        intent: str = "general",
        agents_to_invoke: list[str] | None = None,
        conversation_id: str | None = None,
        **kwargs
    ) -> dict[str, Any]:
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

            # ── AGT-002: concurrently, not in a for-loop ──────────────────
            #
            # This ran agents SEQUENTIALLY, so a four-agent answer waited for
            # the sum of four LLM round-trips. `backend.orchestrator.parallel`
            # was written for exactly this, was fully tested, and nothing
            # called it — the live /chat/query path used the loop below while
            # AGT-002 was recorded as having concurrency.
            #
            # `fan_out` takes FACTORIES rather than coroutines so nothing
            # starts until it gathers, and it turns a per-agent timeout or
            # exception into an `AgentRun(ok=False)` rather than failing the
            # whole response — which is the second acceptance criterion and was
            # also only true in the uncalled module.
            factories = {
                name: partial(
                    self.agents[name].execute,
                    user_query=user_query,
                    user_context=user_context,
                    tools=self.tools,
                )
                for name in agents_to_invoke
                if name in self.agents
            }
            for missing in set(agents_to_invoke) - set(factories):
                logger.warning(f"Agent {missing} not found")

            fan = await fan_out(factories)
            logger.info(
                "%d agent(s) in %.0fms wall clock (sequential would have been "
                "the sum, not the max)", len(fan.runs), fan.wall_ms,
            )

            results = {}
            execution_log = []
            for run in fan.runs:
                if run.ok:
                    result = run.result
                    results[run.name] = result
                    status = (
                        result.status if hasattr(result, "status")
                        else result.get("status", "success")
                        if isinstance(result, dict) else "success"
                    )
                    confidence = (
                        result.confidence if hasattr(result, "confidence")
                        else result.get("confidence", 0.0)
                        if isinstance(result, dict) else 0.0
                    )
                else:
                    # A failure is a first-class result. The distinction
                    # between "timed out" and "raised" is kept because they
                    # need different things from whoever reads the log.
                    status = "timeout" if run.timed_out else "error"
                    confidence = 0.0
                    results[run.name] = {"status": status, "error": run.error}
                    logger.error("Agent %s %s: %s", run.name, status, run.error)

                execution_log.append({
                    "agent": run.name,
                    "status": status,
                    "time_ms": round(run.latency_ms, 1),
                    "confidence": confidence,
                })

            # Aggregate validation reports from all agents
            all_warnings = []
            all_corrections = []
            all_sources = []
            confidence_scores = []

            for agent_result in results.values():
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
orchestrator: AgentOrchestrator | None = AgentOrchestrator()


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


def get_orchestrator() -> AgentOrchestrator | None:
    """Get orchestrator instance."""
    return orchestrator
