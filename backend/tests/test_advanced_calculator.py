import pytest
from typing import Dict, Any

from backend.agents.advanced_calculator import AdvancedCalculatorAgent
from backend.orchestrator.intent_detector import _get_agents_for_intent, Intent


class MockCalcToolExecutor:
    """Mock Tool Executor for testing AdvancedCalculatorAgent."""
    def __init__(self, salary=800000, business=200000, rental=50000, deductions_claimed=120000):
        self.salary = salary
        self.business = business
        self.rental = rental
        self.deductions_claimed = deductions_claimed
        self.called_tools = []
        
    def list_tools(self):
        return ["get_user_income_history", "get_user_deductions", "calculate_tax_liability"]
        
    async def execute_tool(self, name, **kwargs):
        self.called_tools.append((name, kwargs))
        if name == "get_user_income_history":
            return {
                "success": True,
                "result": {
                    "income_history": [
                        {
                            "salary_income": self.salary,
                            "business_income": self.business,
                            "rental_income": self.rental
                        }
                    ]
                }
            }
        elif name == "get_user_deductions":
            return {
                "success": True,
                "result": {
                    "deductions": {
                        "80C": {
                            "claimed": self.deductions_claimed
                        }
                    }
                }
            }
        elif name == "calculate_tax_liability":
            total_income = kwargs.get("total_income", 0)
            deductions = kwargs.get("deductions", 0)
            taxable = max(0, total_income - deductions)
            # Standard slab math
            tax = 0
            if taxable > 250000:
                tax += min(taxable - 250000, 250000) * 0.05
            if taxable > 500000:
                tax += min(taxable - 500000, 500000) * 0.20
            if taxable > 1000000:
                tax += (taxable - 1000000) * 0.30
            return {
                "success": True,
                "result": {
                    "total_tax_liability": tax
                }
            }
        return {"success": False, "error": f"Tool {name} not found"}


@pytest.mark.asyncio
async def test_advanced_calculator_agent_normal_run():
    """Test AdvancedCalculatorAgent executes and calculates correct tax breakdowns."""
    agent = AdvancedCalculatorAgent()
    mock_tools = MockCalcToolExecutor(salary=600000, business=100000, rental=30000, deductions_claimed=150000)
    
    user_context = {
        "user_id": "user-123",
        "long_term_gains": 50000,
        "short_term_gains": 20000,
        "losses": {
            "business": 0,
            "capital": 10000
        },
        "tds_paid": 50000
    }
    
    output = await agent.execute(
        user_query="Calculate my total tax liability with capital gains",
        user_context=user_context,
        tools=mock_tools
    )
    
    assert output.status == "success"
    assert output.agent_name == "advanced_calculator_agent"
    
    res = output.result
    # gross_income = salary (600k) + business (100k) + rental (30k) + stcg (20k) + ltcg (50k) = 800,000
    assert res["gross_income"] == 800000
    assert res["income_breakdown"]["salary"] == 600000
    assert res["income_breakdown"]["capital_gains_ltcg"] == 50000
    assert res["deductions"]["claimed"] == 150000
    # taxable_income = 800k - 150k = 650k
    assert res["taxable_income"] == 650000
    assert "total_tax_liability" in res
    assert res["effective_tax_rate"] > 0
    assert "loss_setoff_details" in res
    assert len(res["optimization_suggestions"]) > 0


def test_calc_intent_routing():
    """Test that TAX_CALCULATION intent routes to advanced_calculator_agent."""
    agents = _get_agents_for_intent(Intent.TAX_CALCULATION)
    assert "advanced_calculator_agent" in agents
