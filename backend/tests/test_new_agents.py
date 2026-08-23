
import pytest

from backend.agents.cross_border_tax import CrossBorderTaxAgent
from backend.agents.price_intelligence import PriceIntelligenceAgent
from backend.agents.tax_strategy import TaxStrategyAgent
from backend.agents.wealth_planner import WealthPlannerAgent
from backend.orchestrator.intent_detector import Intent, _get_agents_for_intent


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
    # AGT-001: this used to assert `estimated_ftc_relief > 0`, which passed
    # because the agent multiplied foreign income by an assumed 30% marginal
    # rate. The test was asserting the fabrication. Eligibility is knowable
    # from the facts given; the AMOUNT is not, because Rule 128 computes the
    # credit per country and per head of income against the taxpayer's whole
    # Indian position, so it stays None rather than becoming a guess.
    assert output.result["ftc_relief"] is None
    recommendations = output.result["recommendations"]
    assert any("Schedule FA" in rec for rec in recommendations)
    # The certain parts are still stated: the test, the cap, and Form 67.
    assert any("lower of" in rec.lower() for rec in recommendations)
    assert any("Form 67" in rec for rec in recommendations)


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
async def test_price_intelligence_agent_needs_dates_not_years():
    """PRC-008 changed the contract, and the change is the point.

    v1 took `purchase_year: "2015-16"` and `sell_year: "2024-25"`. A YEAR is
    not enough: FY 2024-25 straddles 23 July 2024, and which side of that date
    a transfer falls on decides whether indexation is available at all. The
    agent now requires the actual dates and names them when they are absent
    rather than indexing against a guessed year.
    """
    agent = PriceIntelligenceAgent()
    output = await agent.execute(
        user_query="Calculate my indexation tax benefits for property sale",
        user_context={"user_id": "user-123", "asset_type": "immovable_property"},
        tools=MockAgentToolExecutor(income=1000000),
    )

    assert output.status == "needs_input"
    assert "acquired_on" in output.result["missing_fields"]
    assert "sold_on" in output.result["missing_fields"]


@pytest.mark.asyncio
async def test_price_intelligence_agent_declines_yield_comparison():
    """v1 returned four instruments ranked by post-tax yield, every figure
    invented, and recommended Sovereign Gold Bonds that cannot be bought at
    primary issue. The comparison is gone, not corrected: ranking investments
    by projected return is SEBI-regulated advice."""
    agent = PriceIntelligenceAgent()
    output = await agent.execute(
        user_query="Compare investment returns post tax",
        user_context={"user_id": "user-123", "investment_amount": 200000.0},
        tools=MockAgentToolExecutor(income=1600000),
    )

    assert output.status == "declined"
    assert "yield_comparison" not in output.result
    assert "SEBI" in output.result["explanation"]
    assert "February 2024" in output.result["sovereign_gold_bonds"]


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
