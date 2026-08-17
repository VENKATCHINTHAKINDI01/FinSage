"""
Base agent class for all FinSage agents.
Each agent inherits from this and implements execute() method.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AgentOutput:
    """Standardized agent output."""
    agent_name: str
    intent: str = "general"
    status: str = "success"
    result: dict = None
    confidence: float = 0.0
    reasoning: str = ""
    execution_time_ms: float = 0
    timestamp: str = None
    # Validation metadata
    validation_report: dict = None
    data_sources_used: list = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if self.result is None:
            self.result = {}
        if self.validation_report is None:
            self.validation_report = {
                "is_valid": True,
                "confidence_score": self.confidence,
                "warnings": [],
                "corrections_applied": [],
                "sources_verified": []
            }
        if self.data_sources_used is None:
            self.data_sources_used = []


class BaseAgent(ABC):
    """
    Base class for all FinSage agents.
    
    Each agent specializes in one domain:
    - Tax agents: deductions, savings strategies
    - Investment agents: portfolio analysis, recommendations
    - Benefits agents: government schemes, eligibility
    - etc.
    """

    def __init__(self, name: str, intent: str):
        """
        Initialize agent.
        
        Args:
            name: Agent name (e.g., "tax_deduction_agent")
            intent: What this agent handles (e.g., "tax_deduction")
        """
        self.name = name
        self.intent = intent
        self.logger = logging.getLogger(f"agent.{name}")

    @abstractmethod
    async def execute(
        self,
        user_query: str,
        user_context: dict[str, Any],
        **kwargs
    ) -> AgentOutput:
        """
        Execute agent logic.
        
        Args:
            user_query: User's question
            user_context: User data (income, profile, etc.)
            **kwargs: Additional parameters
        
        Returns:
            AgentOutput with result
        """
        pass

    async def preprocess(self, user_query: str) -> str:
        """
        Preprocess query (normalize, extract keywords, etc.).
        Override if needed.
        """
        return user_query.lower().strip()

    async def postprocess(self, result: dict[str, Any]) -> dict[str, Any]:
        """
        Postprocess result — runs validation on the output.
        Override if needed.
        """
        try:
            from backend.tools.data_validator import LLMResponseValidator
            validator = LLMResponseValidator()

            # Validate deductions if present
            deductions = result.get("deductions") or result.get("deductions_found")
            if deductions and isinstance(deductions, list):
                validated_deductions, report = validator.validate_deductions(deductions)
                result["deductions"] = validated_deductions
                if "deductions_found" in result:
                    result["deductions_found"] = validated_deductions
                result["_validation_report"] = report.to_dict()

            # Validate income sources if present
            sources = result.get("income_sources")
            if sources and isinstance(sources, list):
                validated_sources, report = validator.validate_income_sources(sources)
                result["income_sources"] = validated_sources
                result["_validation_report"] = report.to_dict()

        except Exception as e:
            self.logger.warning(f"Postprocess validation skipped: {e}")

        return result

    def _create_output(
        self,
        result: dict[str, Any],
        status: str = "success",
        confidence: float = 1.0,
        reasoning: str = "",
        execution_time_ms: float = 0.0
    ) -> AgentOutput:
        """Helper to create standardized output."""
        # Extract validation report if present
        validation_report = result.pop("_validation_report", None)
        data_sources = result.pop("_data_sources", None)

        return AgentOutput(
            agent_name=self.name,
            intent=self.intent,
            status=status,
            result=result,
            confidence=confidence,
            reasoning=reasoning,
            execution_time_ms=execution_time_ms,
            timestamp=datetime.now(timezone.utc).isoformat(),
            validation_report=validation_report,
            data_sources_used=data_sources or []
        )


class TaxAgent(ABC):
    """Base class for tax agents with tool support."""

    def __init__(self, name: str, intent: str = ""):
        self.name = name
        self.intent = intent
        self.tools = None
        self.logger = logging.getLogger(f"agent.{name}")

    def set_tools(self, tools) -> "TaxAgent":
        """Inject tools into agent."""
        self.tools = tools
        self.logger.info(f"Tools injected ({len(tools.list_tools())} available)")
        return self

    async def call_tool(self, tool_name: str, **kwargs) -> dict:
        """Call a tool via executor."""
        if not self.tools:
            self.logger.error("Tools not initialized")
            return {"success": False, "error": "Tools not initialized"}

        self.logger.debug(f"Calling tool: {tool_name}")
        return await self.tools.execute_tool(tool_name, **kwargs)

    @abstractmethod
    async def execute(
        self,
        user_query: str,
        user_context: dict,
        tools=None,
        **kwargs
    ) -> AgentOutput:
        """Execute the agent with optional tool support."""
        pass

    async def preprocess(self, query: str) -> str:
        """Preprocess user query."""
        return query.strip().lower()

    async def postprocess(self, result: dict) -> dict:
        """Postprocess agent result — runs validation."""
        try:
            from backend.tools.data_validator import LLMResponseValidator
            validator = LLMResponseValidator()

            # Validate deductions if present
            deductions = result.get("deductions") or result.get("deductions_found")
            if deductions and isinstance(deductions, list):
                validated_deductions, report = validator.validate_deductions(deductions)
                result["deductions"] = validated_deductions
                if "deductions_found" in result:
                    result["deductions_found"] = validated_deductions
                result["_validation_report"] = report.to_dict()

            # Validate income sources if present
            sources = result.get("income_sources")
            if sources and isinstance(sources, list):
                validated_sources, report = validator.validate_income_sources(sources)
                result["income_sources"] = validated_sources
                result["_validation_report"] = report.to_dict()

        except Exception as e:
            self.logger.warning(f"Postprocess validation skipped: {e}")

        return result

    def _create_output(
        self,
        result: dict,
        status: str = "success",
        confidence: float = 0.8,
        reasoning: str = "",
        execution_time_ms: float = 0
    ) -> AgentOutput:
        """Create standardized output."""
        # Extract validation report if present
        validation_report = result.pop("_validation_report", None) if isinstance(result, dict) else None
        data_sources = result.pop("_data_sources", None) if isinstance(result, dict) else None

        return AgentOutput(
            agent_name=self.name,
            intent=self.intent,
            status=status,
            result=result,
            confidence=confidence,
            reasoning=reasoning,
            execution_time_ms=execution_time_ms,
            timestamp=datetime.now(timezone.utc).isoformat(),
            validation_report=validation_report,
            data_sources_used=data_sources or []
        )


class InvestmentAgent(BaseAgent):
    """Base class for investment-focused agents"""

    def __init__(self, name: str):
        super().__init__(name, "investment_related")


class BenefitsAgent(BaseAgent):
    """Base class for government benefits agents"""

    def __init__(self, name: str):
        super().__init__(name, "benefits_related")

# ═══════════════════════════════════════════════════════════════════════════
# EVD-003 — confidence is measured, not authored
# ═══════════════════════════════════════════════════════════════════════════

def derive_confidence(
    *,
    tool_results: list | dict | None = None,
    used_llm_for_values: bool = False,
    missing_inputs: list[str] | None = None,
    assumptions: dict[str, str] | None = None,
    error: str | None = None,
):
    """Build a Confidence from what actually happened during this execution.

    What this replaces
    ------------------
    Ten agents each returned a hand-picked constant — 0.80, 0.85, 0.88, 0.90,
    0.92, 0.95 — rendered to users as a quality percentage. Nobody could say why
    the ITR helper was 0.92 and the deduction hunter 0.80. They were not
    measurements; they were decoration that looked like measurement, which
    spends trust the system has not earned.

    Separately, `ValidationReport.add_warning` subtracted a flat 0.1 per warning
    regardless of what the warning said, so a cosmetic formatting note cost the
    same as a failed limit check.

    Confidence now derives from signals that exist at runtime: whether tools
    actually returned, which inputs were absent, what was assumed, and whether a
    model touched a value it should not have.
    """
    from backend.core.provenance.confidence import Confidence, Provenance

    conf = Confidence()

    if error:
        conf.missing("a successful computation", error, blocks=True)
        return conf

    results = tool_results if isinstance(tool_results, list) else [tool_results] if tool_results else []
    succeeded = [r for r in results if isinstance(r, dict) and r.get("success")]
    if results and not succeeded:
        conf.missing(
            "tool results",
            "no tool call returned successfully, so nothing here is grounded",
            blocks=True,
        )
        return conf

    for field_name in missing_inputs or []:
        conf.missing(field_name, "excluded from the calculation")

    for what, value in (assumptions or {}).items():
        conf.assumption(what, value)

    # Should never fire: the core computes every figure. If it does, the answer
    # is not deterministic and must not be presented as exact.
    if used_llm_for_values:
        conf.llm_generated("a figure in this result")

    # Values the user typed rather than a document we parsed.
    if not results:
        conf.input_from("user profile", Provenance.USER_STATED)

    return conf


def confidence_score(conf) -> float:
    """Confidence as a float, for the legacy `AgentOutput.confidence` field.

    The conversion lives here rather than in backend/core because the core bans
    float construction outright — a Decimal-to-float hop is harmless for a 0–1
    ratio, but carving an exception into a purity rule is how purity rules stop
    being enforced. AGT-001 replaces this field with the full breakdown.
    """
    return float(conf.score)
