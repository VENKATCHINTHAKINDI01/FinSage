import pytest
from typing import Dict, Any

from backend.agents.cross_border_tax import CrossBorderTaxAgent
from backend.agents.price_intelligence import PriceIntelligenceAgent
from backend.agents.tax_strategy import TaxStrategyAgent
from backend.agents.wealth_planner import WealthPlannerAgent
from backend.orchestrator.intent_detector import _get_agents_for_intent, Intent


class MockAgentToolExecutor:
    """Mock Tool Executor for testing the new agents."""
    def __init__(self, income=1200000, deductions=None, investments=None):
        self.income = income
        self.deductions = deductions or []
        self.investments = investments or {}
        
    def list_tools(self):
        return ["get_user_profile", "get_user_deductions", "get_user_investments"]
        
    async def execute_tool(self, name, **kwargs):
        if name == "get_user_profile":
            return {
                "success": True,
                "result": {
                    "basic_info": {
                        "age": 35,
                        "employment_type": "salaried",
                        "days_in_india": 185
                    },
                    "financial_profile": {
                        "annual_income": self.income
                    }
                }
            }
        elif name == "get_user_deductions":
            return {
                "success": True,
                "result": {
                    "deductions": self.deductions
                }
            }
        elif name == "get_user_investments":
            return {
                "success": True,
                "result": {
                    "investments": self.investments
                }
            }
        return {"success": False, "error": f"Tool {name} not found"}


@pytest.mark.asyncio
async def test_cross_border_tax_agent_resident():
    """Test CrossBorderTaxAgent under Resident stays."""
    agent = CrossBorderTaxAgent()
    mock_tools = MockAgentToolExecutor(income=800000)
    
    # Stay >= 182 days and Ordinarily Resident (ROR)
    user_context = {
        "user_id": "user-123",
        "days_in_india": 190,
        "nri_prev_10_years": 0,
        "stay_prev_7_years": 1000,
        "has_foreign_assets": True,
        "foreign_income": 500000.0,
        "foreign_tax_paid": 100000.0,
        "foreign_country": "US"
    }
    output = await agent.execute(
        user_query="What are my foreign assets disclosure rules?",
        user_context=user_context,
        tools=mock_tools
    )
    
    assert output.status == "success"
    assert "Resident" in output.result["residential_status"]
    assert output.result["schedule_fa_required"] is True
    assert output.result["dtaa_relief_eligible"] is True
    assert output.result["estimated_ftc_relief"] > 0
    assert any("Schedule FA" in rec for rec in output.result["recommendations"])


@pytest.mark.asyncio
async def test_cross_border_tax_agent_nri():
    """Test CrossBorderTaxAgent under Non-Resident stays."""
    agent = CrossBorderTaxAgent()
    mock_tools = MockAgentToolExecutor(income=800000)
    
    # Stay < 60 days
    user_context = {
        "user_id": "user-123",
        "days_in_india": 45,
        "is_citizen_or_pio": False
    }
    output = await agent.execute(
        user_query="Am I NRI?",
        user_context=user_context,
        tools=mock_tools
    )
    
    assert output.status == "success"
    assert "Non-Resident Indian (NRI)" in output.result["residential_status"]
    assert output.result["schedule_fa_required"] is False


@pytest.mark.asyncio
async def test_price_intelligence_agent_cii():
    """Test PriceIntelligenceAgent Cost Inflation Index calculation."""
    agent = PriceIntelligenceAgent()
    mock_tools = MockAgentToolExecutor(income=1000000)
    
    user_context = {
        "user_id": "user-123",
        "asset_type": "real_estate",
        "purchase_year": "2015-16", # CII: 254
        "sell_year": "2024-25", # CII: 363
        "purchase_price": 5000000.0,
        "sale_price": 8000000.0
    }
    output = await agent.execute(
        user_query="Calculate my indexation tax benefits for property sale",
        user_context=user_context,
        tools=mock_tools
    )
    
    assert output.status == "success"
    assert output.result["calculation_type"] == "indexation_ltcg"
    # Indexed Cost: 50L * (363 / 254) = ~71.45L
    assert 7100000.0 < output.result["indexed_cost"] < 7200000.0
    assert output.result["capital_gains"] > 0
    assert output.result["estimated_ltcg_tax"] > 0
    assert any("indexed cost" in rec.lower() for rec in output.result["recommendations"])


@pytest.mark.asyncio
async def test_price_intelligence_agent_yields():
    """Test PriceIntelligenceAgent post-tax yield comparison."""
    agent = PriceIntelligenceAgent()
    mock_tools = MockAgentToolExecutor(income=1600000) # Marginal 30% slab
    
    user_context = {
        "user_id": "user-123",
        "investment_amount": 200000.0
    }
    output = await agent.execute(
        user_query="Compare investment returns post tax",
        user_context=user_context,
        tools=mock_tools
    )
    
    assert output.status == "success"
    assert output.result["calculation_type"] == "post_tax_yields"
    assert len(output.result["yield_comparison"]) == 4
    # FD yield post tax should be 7.5% * (1 - 0.3) = 5.25%
    fd_data = next(item for item in output.result["yield_comparison"] if "Fixed Deposit" in item["instrument"])
    assert fd_data["post_tax_yield"] == "5.25%"


@pytest.mark.asyncio
async def test_tax_strategy_agent():
    """Test TaxStrategyAgent 3-year projections and harvesting advice."""
    agent = TaxStrategyAgent()
    mock_tools = MockAgentToolExecutor(
        income=1200000,
        deductions=[{"category": "80C", "amount": 150000}]
    )
    
    user_context = {"user_id": "user-123"}
    output = await agent.execute(
        user_query="Old vs New tax regime projection strategy",
        user_context=user_context,
        tools=mock_tools
    )
    
    assert output.status == "success"
    assert len(output.result["three_year_projections"]) == 3
    assert "old_regime_deductions_applied" in output.result
    assert any("Harvesting" in rec for rec in output.result["recommendations"])


@pytest.mark.asyncio
async def test_wealth_planner_agent():
    """Test WealthPlannerAgent retirement NPS/PPF planning and 54EC bonds."""
    agent = WealthPlannerAgent()
    mock_tools = MockAgentToolExecutor(
        income=1000000,
        investments={"nps": 2000000.0, "ppf": 800000.0}
    )
    
    # Capital gains to reinvest
    user_context = {
        "user_id": "user-123",
        "capital_gain": 6000000.0
    }
    output = await agent.execute(
        user_query="Plan my retirement NPS and property gain reinvestment",
        user_context=user_context,
        tools=mock_tools
    )
    
    assert output.status == "success"
    # NPS Lump sum = 20L * 60% = 12L
    assert output.result["nps_tax_free_lump_sum_60_percent"] == 1200000.0
    # 54EC bonds cap at 50L
    assert any("Section 54EC Bonds" in rec for rec in output.result["recommendations"])
    assert any("capped at ₹50 Lakhs" in rec for rec in output.result["recommendations"])


def test_new_agents_intent_routing():
    """Test intent routing maps correctly for the new categories."""
    assert "cross_border_tax_agent" in _get_agents_for_intent(Intent.CROSS_BORDER_TAX)
    assert "price_intelligence_agent" in _get_agents_for_intent(Intent.PRICE_INTELLIGENCE)
    assert "tax_strategy_agent" in _get_agents_for_intent(Intent.TAX_STRATEGY)
    assert "wealth_planner_agent" in _get_agents_for_intent(Intent.WEALTH_PLANNING)
