import pytest
from typing import Dict, Any

from backend.agents.compliance_checker import ComplianceCheckerAgent
from backend.orchestrator.intent_detector import _get_agents_for_intent, Intent


class MockComplianceToolExecutor:
    """Mock Tool Executor for testing ComplianceCheckerAgent."""
    def __init__(self, income=2500000, has_deductions=True):
        self.income = income
        self.has_deductions = has_deductions
        self.called_tools = []
        
    def list_tools(self):
        return ["get_user_profile", "get_user_deductions"]
        
    async def execute_tool(self, name, **kwargs):
        self.called_tools.append((name, kwargs))
        if name == "get_user_profile":
            return {
                "success": True,
                "result": {
                    "basic_info": {
                        "age": 35,
                        "employment_type": "salaried"
                    },
                    "financial_profile": {
                        "annual_income": self.income,
                        "other_income": 50000,
                        "investments": {
                            "elss": 100000 if self.has_deductions else 0
                        }
                    }
                }
            }
        elif name == "get_user_deductions":
            deductions = []
            if self.has_deductions:
                deductions = [
                    {"category": "80C", "amount": 100000},
                    {"category": "80D", "amount": 25000}
                ]
            return {
                "success": True,
                "result": {
                    "deductions": deductions
                }
            }
        return {"success": False, "error": f"Tool {name} not found"}


@pytest.mark.asyncio
async def test_compliance_checker_agent_high_compliance():
    """Test ComplianceCheckerAgent under a healthy, compliant profile."""
    agent = ComplianceCheckerAgent()
    # Moderate income with deductions and files complete documentation
    mock_tools = MockComplianceToolExecutor(income=450000, has_deductions=True)
    
    user_context = {"user_id": "user-123"}
    output = await agent.execute(
        user_query="How is my compliance status?",
        user_context=user_context,
        tools=mock_tools
    )
    
    assert output.status == "success"
    assert output.agent_name == "compliance_checker_agent"
    assert "compliance_score" in output.result
    assert output.result["compliance_score"] >= 80
    assert output.result["audit_ready"] is True
    assert len(output.result["missing_documents"]) == 0
    assert output.result["risk_level"] == "🟢 Low Risk - Audit unlikely"


@pytest.mark.asyncio
async def test_compliance_checker_agent_low_compliance_red_flags():
    """Test ComplianceCheckerAgent with high income, missing documents, and red flags."""
    agent = ComplianceCheckerAgent()
    # High income with zero deductions will trigger red flags
    mock_tools = MockComplianceToolExecutor(income=2500000, has_deductions=False)
    
    user_context = {"user_id": "user-123"}
    output = await agent.execute(
        user_query="Verify my audit readiness",
        user_context=user_context,
        tools=mock_tools
    )
    
    assert output.status == "success"
    # Score should drop because of red flags (high income, low deductions, large cash transaction, foreign travel)
    assert output.result["compliance_score"] < 80
    assert output.result["audit_ready"] is False
    assert len(output.result["red_flags"]) > 0
    assert "High income with low deductions" in output.result["red_flags"][0]["flag"]


def test_compliance_intent_routing():
    """Test that COMPLIANCE_CHECK intent is routed to compliance_checker_agent."""
    agents = _get_agents_for_intent(Intent.COMPLIANCE_CHECK)
    assert "compliance_checker_agent" in agents
