import pytest
from typing import Dict, Any

from backend.agents.itr_helper import ITRHelperAgent
from backend.orchestrator.intent_detector import _get_agents_for_intent, Intent


class MockITRToolExecutor:
    """Mock Tool Executor for testing ITRHelperAgent."""
    def __init__(self, income=400000, employment_type="salaried", has_capital_gains=False):
        self.income = income
        self.employment_type = employment_type
        self.has_capital_gains = has_capital_gains
        self.called_tools = []
        
    def list_tools(self):
        return ["get_user_profile"]
        
    async def execute_tool(self, name, **kwargs):
        self.called_tools.append((name, kwargs))
        if name == "get_user_profile":
            return {
                "success": True,
                "result": {
                    "basic_info": {
                        "age": 35,
                        "employment_type": self.employment_type
                    },
                    "financial_profile": {
                        "annual_income": self.income
                    }
                }
            }
        return {"success": False, "error": f"Tool {name} not found"}


@pytest.mark.asyncio
async def test_itr_helper_agent_salaried_itr1():
    """Test ITRHelperAgent recommends ITR-1 for lower income salaried individuals."""
    agent = ITRHelperAgent()
    mock_tools = MockITRToolExecutor(income=450000, employment_type="salaried")
    
    user_context = {"user_id": "user-123"}
    output = await agent.execute(
        user_query="Which ITR form should I file?",
        user_context=user_context,
        tools=mock_tools
    )
    
    assert output.status == "success"
    assert output.agent_name == "itr_helper_agent"
    assert output.result["recommended_form"] == "ITR-1"
    assert "Salary" in output.result["form_details"]["income_types"]
    assert len(output.result["step_by_step_guide"]) > 0
    assert "incometax.gov.in" in output.result["step_by_step_guide"][0]["action"]


@pytest.mark.asyncio
async def test_itr_helper_agent_business_itr4():
    """Test ITRHelperAgent recommends ITR-4 for business/self-employed individuals."""
    agent = ITRHelperAgent()
    mock_tools = MockITRToolExecutor(income=800000, employment_type="business")
    
    user_context = {"user_id": "user-123"}
    output = await agent.execute(
        user_query="Guide me on self-employed ITR filing",
        user_context=user_context,
        tools=mock_tools
    )
    
    assert output.status == "success"
    assert output.result["recommended_form"] == "ITR-4"
    assert "Business" in output.result["form_details"]["income_types"]


@pytest.mark.asyncio
async def test_itr_helper_agent_high_income_itr5():
    """Test ITRHelperAgent recommends ITR-5 for very high income individuals (> 50L)."""
    agent = ITRHelperAgent()
    mock_tools = MockITRToolExecutor(income=6000000, employment_type="salaried")
    
    user_context = {"user_id": "user-123"}
    output = await agent.execute(
        user_query="ITR form for 60L salary?",
        user_context=user_context,
        tools=mock_tools
    )
    
    assert output.status == "success"
    assert output.result["recommended_form"] == "ITR-5"


def test_itr_intent_routing():
    """Test that TAX_FILING intent is routed to itr_helper_agent."""
    agents = _get_agents_for_intent(Intent.TAX_FILING)
    assert "itr_helper_agent" in agents
