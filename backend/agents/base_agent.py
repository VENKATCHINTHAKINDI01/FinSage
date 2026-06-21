"""
Base agent class for all FinSage agents.
Each agent inherits from this and implements execute() method.
"""

from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging
from datetime import datetime
from dataclasses import dataclass

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
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat()
        if self.result is None:
            self.result = {}


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
        user_context: Dict[str, Any],
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
    
    async def postprocess(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Postprocess result (format, validate, etc.).
        Override if needed.
        """
        return result
    
    def _create_output(
        self,
        result: Dict[str, Any],
        status: str = "success",
        confidence: float = 1.0,
        reasoning: str = "",
        execution_time_ms: float = 0.0
    ) -> AgentOutput:
        """Helper to create standardized output."""
        return AgentOutput(
            agent_name=self.name,
            intent=self.intent,
            status=status,
            result=result,
            confidence=confidence,
            reasoning=reasoning,
            execution_time_ms=execution_time_ms,
            timestamp=datetime.utcnow()
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
        """Postprocess agent result."""
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
        return AgentOutput(
            agent_name=self.name,
            intent=self.intent,
            status=status,
            result=result,
            confidence=confidence,
            reasoning=reasoning,
            execution_time_ms=execution_time_ms,
            timestamp=datetime.utcnow().isoformat()
        )


class InvestmentAgent(BaseAgent):
    """Base class for investment-focused agents"""
    
    def __init__(self, name: str):
        super().__init__(name, "investment_related")


class BenefitsAgent(BaseAgent):
    """Base class for government benefits agents"""
    
    def __init__(self, name: str):
        super().__init__(name, "benefits_related")