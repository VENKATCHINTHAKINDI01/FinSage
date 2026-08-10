"""Agent orchestration.

Imports here are LAZY on purpose.

The previous version eagerly imported `advanced_orchestrator`, which imports
langgraph. That made langgraph a hard requirement for touching *any* module in
this package — including `parallel`, which has no LLM dependency at all and is
pure asyncio. A test of the fan-out logic could not run without installing a
graph framework it never uses.

A package `__init__` that pulls in the heaviest thing in the package taxes
every import in it. `__getattr__` (PEP 562) keeps the public names available
while deferring the cost to first actual use.
"""

from __future__ import annotations

from typing import Any

# Cheap, dependency-free, and used almost everywhere — worth importing eagerly.
from backend.orchestrator.parallel import AgentRun, FanOutResult, fan_out

_LAZY = {
    "AgentState": "backend.orchestrator.agent_state",
    "create_initial_state": "backend.orchestrator.agent_state",
    "intent_router": "backend.orchestrator.router_nodes",
    "should_run_income_classifier": "backend.orchestrator.router_nodes",
    "income_classifier_node": "backend.orchestrator.execution_nodes",
    "deduction_hunter_node": "backend.orchestrator.execution_nodes",
    "tax_optimizer_node": "backend.orchestrator.execution_nodes",
    "ConversationMemory": "backend.orchestrator.memory",
    "SemanticMemory": "backend.orchestrator.memory",
    "generate_response": "backend.orchestrator.response_generation",
    # These three need langgraph. Deferred so its absence only matters when
    # something actually asks for them.
    "AdvancedAgentOrchestrator": "backend.orchestrator.advanced_orchestrator",
    "LangGraphBuilder": "backend.orchestrator.advanced_orchestrator",
    "run_workflow": "backend.orchestrator.advanced_orchestrator",
}


def __getattr__(name: str) -> Any:
    module_path = _LAZY.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    import importlib

    return getattr(importlib.import_module(module_path), name)


def __dir__() -> list[str]:
    return sorted([*_LAZY, "AgentRun", "FanOutResult", "fan_out"])


__all__ = [
    "AdvancedAgentOrchestrator",
    "AgentRun",
    "AgentState",
    "ConversationMemory",
    "FanOutResult",
    "SemanticMemory",
    "create_initial_state",
    "fan_out",
    "generate_response",
    "run_workflow",
]
