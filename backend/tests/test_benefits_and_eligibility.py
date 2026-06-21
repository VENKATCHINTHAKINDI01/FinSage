import pytest
import pytest_asyncio
from typing import Dict, Any

from backend.tools.schemes_search import SchemeLookupTool, GovernmentSchemesDatabase
from backend.agents.benefits_discovery import BenefitsDiscoveryAgent
from backend.agents.eligibility_verifier import EligibilityVerifierAgent
from backend.orchestrator.intent_detector import _get_agents_for_intent, Intent


class MockToolExecutor:
    """Mock Tool Executor for testing agents without DB dependencies."""
    def __init__(self, age=35, has_health_insurance=True, has_education_loan=False):
        self.called_tools = []
        self.age = age
        self.has_health_insurance = has_health_insurance
        self.has_education_loan = has_education_loan
        
    def list_tools(self):
        return ["get_user_profile", "get_applicable_schemes", "get_scheme_details", "check_scheme_eligibility"]
        
    async def execute_tool(self, name, **kwargs):
        self.called_tools.append((name, kwargs))
        if name == "get_user_profile":
            return {
                "success": True,
                "result": {
                    "basic_info": {
                        "age": self.age,
                        "employment_type": "salaried"
                    },
                    "financial_profile": {
                        "annual_income": 600000,
                        "insurance": {
                            "health_insurance": self.has_health_insurance
                        },
                        "loans": {
                            "education_loan": 50000 if self.has_education_loan else 0
                        }
                    }
                }
            }
        elif name == "get_applicable_schemes":
            return {
                "success": True,
                "result": {
                    "applicable_schemes": [
                        {"code": "80C", "name": "Section 80C", "limit": 150000, "recommendation_strength": "High"},
                        {"code": "80D", "name": "Section 80D", "limit": 75000, "recommendation_strength": "High"}
                    ]
                }
            }
        elif name == "get_scheme_details":
            return {
                "success": True,
                "result": {
                    "details": {
                        "name": "Health Insurance Premium",
                        "limit": 75000,
                        "description": "Deduction on health insurance premiums",
                        "benefits": ["Tax deduction on premium paid"],
                        "documents_needed": ["Premium receipt"]
                    }
                }
            }
        elif name == "check_scheme_eligibility":
            code = kwargs.get("scheme_code", "")
            eligible = True
            reasons = ["Meets criteria"]
            if code == "80D" and not kwargs.get("has_health_insurance", False):
                eligible = False
                reasons = ["No health insurance"]
            elif code == "80E" and not kwargs.get("has_education_loan", False):
                eligible = False
                reasons = ["No education loan"]
            return {
                "success": True,
                "result": {
                    "eligible": eligible,
                    "reasons": reasons
                }
            }
        return {"success": False, "error": f"Tool {name} not found"}


@pytest.mark.asyncio
async def test_scheme_lookup_tool_eligibility():
    """Test the in-memory SchemeLookupTool directly."""
    tool = SchemeLookupTool()
    
    # 80D with health insurance
    res = await tool.check_scheme_eligibility(
        scheme_code="80D",
        user_age=30,
        user_income=500000,
        has_health_insurance=True
    )
    assert res["success"] is True
    assert res["eligible"] is True
    
    # 80D without health insurance
    res_no_ins = await tool.check_scheme_eligibility(
        scheme_code="80D",
        user_age=30,
        user_income=500000,
        has_health_insurance=False
    )
    assert res_no_ins["success"] is True
    assert res_no_ins["eligible"] is False
    assert "health insurance" in res_no_ins["reasons"][0]


@pytest.mark.asyncio
async def test_benefits_discovery_agent_execute():
    """Test execution flow of BenefitsDiscoveryAgent."""
    agent = BenefitsDiscoveryAgent()
    mock_tools = MockToolExecutor()
    
    user_context = {"user_id": "user-123", "age": 35}
    output = await agent.execute(
        user_query="What government schemes do I qualify for?",
        user_context=user_context,
        tools=mock_tools
    )
    
    assert output.status == "success"
    assert output.agent_name == "benefits_discovery_agent"
    assert output.result["schemes_found"] > 0
    assert "Tax Deductions" in output.result["categories"]
    assert output.result["total_potential_savings"] > 0
    assert len(mock_tools.called_tools) > 0


@pytest.mark.asyncio
async def test_eligibility_verifier_agent_eligible():
    """Test EligibilityVerifierAgent when user qualifies for the scheme."""
    agent = EligibilityVerifierAgent()
    mock_tools = MockToolExecutor(has_health_insurance=True)
    
    user_context = {"user_id": "user-123"}
    output = await agent.execute(
        user_query="Can I claim health insurance deduction under 80D?",
        user_context=user_context,
        tools=mock_tools
    )
    
    assert output.status == "success"
    assert output.result["eligible"] is True
    assert "80D" in output.result["scheme_code"]
    assert "✅ YOU ARE ELIGIBLE" in output.result["status"]


@pytest.mark.asyncio
async def test_eligibility_verifier_agent_ineligible():
    """Test EligibilityVerifierAgent when user does not qualify."""
    agent = EligibilityVerifierAgent()
    # User does not have health insurance, so they don't qualify for 80D
    mock_tools = MockToolExecutor(has_health_insurance=False)
    
    user_context = {"user_id": "user-123"}
    output = await agent.execute(
        user_query="Can I claim 80D?",
        user_context=user_context,
        tools=mock_tools
    )
    
    assert output.status == "success"
    assert output.result["eligible"] is False
    assert "80D" in output.result["scheme_code"]
    assert "❌ NOT ELIGIBLE" in output.result["status"]


def test_intent_routing_maps():
    """Test that the intent detector maps intents to the new agents."""
    benefits_agents = _get_agents_for_intent(Intent.GOVERNMENT_BENEFITS)
    assert "benefits_discovery_agent" in benefits_agents
    
    eligibility_agents = _get_agents_for_intent(Intent.ELIGIBILITY_CHECK)
    assert "eligibility_verifier_agent" in eligibility_agents


def test_benefits_endpoints():
    """Test the newly added benefits discovery & verification API endpoints."""
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend.security.dependencies import get_current_user

    class MockUser:
        id = "user-123"
        email = "test@example.com"
        full_name = "Test User"
        age = 35
        employment_type = "salaried"
        annual_income = 600000
        health_insurance = True
        education_loan = False

    def mock_get_current_user():
        return MockUser()

    app.dependency_overrides[get_current_user] = mock_get_current_user

    # Use context manager to trigger FastAPI startup lifespan
    with TestClient(app) as client:
        # 1. Test GET /schemes
        res = client.get("/api/v1/benefits/schemes")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["total_schemes"] == 9
        assert data["schemes"][0]["code"] == "80C"
        
        # 2. Test POST /discover
        res = client.post("/api/v1/benefits/discover", json={"query": "What schemes do I qualify for?"})
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "schemes_found" in data
        assert "total_potential_savings" in data
        
        # 3. Test POST /verify-eligibility
        res = client.post("/api/v1/benefits/verify-eligibility", json={"scheme_code": "80D"})
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["scheme_code"] == "80D"
        assert "eligible" in data

    # Clear overrides after the test
    app.dependency_overrides.clear()
