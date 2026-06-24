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


def test_compliance_endpoints():
    """Test the newly added compliance, filing and calculator API endpoints."""
    from fastapi.testclient import TestClient
    from unittest.mock import AsyncMock, MagicMock
    from backend.main import app
    from backend.security.dependencies import get_current_user
    from backend.db.postgres import get_session

    class MockUser:
        id = "user-123"
        email = "test@example.com"
        full_name = "Test User"
        age = 35
        employment_type = "salaried"
        annual_income = 600000
        tds_paid = 50000
        deductions = {"80C": 150000}
        gst_registered = False
        advance_tax_paid = 10000
        turnover = 0
        has_capital_gains = False
        calculated_tax = 0
        form_16_tds = 0

    def mock_get_current_user():
        return MockUser()

    async def mock_get_session():
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        yield mock_session

    app.dependency_overrides[get_current_user] = mock_get_current_user
    app.dependency_overrides[get_session] = mock_get_session

    with TestClient(app) as client:
        # 1. Test POST /report
        res = client.post("/api/v1/compliance/report", json={})
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "compliance_score" in data
        assert "audit_ready" in data
        
        # 2. Test POST /filing
        res = client.post("/api/v1/compliance/filing", json={})
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "recommended_form" in data
        assert "step_by_step_guide" in data
        
        # 3. Test POST /calculator
        res = client.post("/api/v1/compliance/calculator", json={
            "income_sources": {"salary_income": 600000},
            "deductions": {"80C": 150000},
            "capital_gains": {"ltcg": 50000, "stcg": 20000},
            "losses": {}
        })
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "gross_income" in data
        assert "effective_tax_rate" in data

        # 4. Test GET /audit-history
        res = client.get("/api/v1/compliance/audit-history")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "history" in data

        # 5. Test GET /itr-status
        res = client.get("/api/v1/compliance/itr-status")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "message" in data or "status" in data

    app.dependency_overrides.clear()
