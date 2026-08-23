import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from backend.main import app
from backend.security.dependencies import get_current_user
from backend.db.postgres import get_session
from backend.api.reports import get_report_generator
from backend.services.report_generator import ReportGenerator
from backend.vault import DocumentVault, MemoryVault


class MockUser:
    id = "test-user-step10-api"
    email = "test_step10@example.com"
    full_name = "Step10 Test User"
    age = 35
    employment_type = "salaried"
    annual_income = 1500000
    tds_paid = 100000
    deductions = {"80C": 150000}
    gst_registered = False
    advance_tax_paid = 20000
    turnover = 0
    has_capital_gains = False


def mock_get_current_user():
    return MockUser()


async def mock_get_session():
    mock_session = AsyncMock()
    
    # Mock return values for ORM queries to prevent crashes
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_result.scalars.return_value.first.return_value = None
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result
    
    yield mock_session


async def mock_get_report_generator():
    """A generator whose documents go to RAM.

    Without this the route built its own generator, which reached the real
    document vault, so this test needed AWS credentials to pass and did not
    have them. The endpoint contract is what is under test here; where the
    bytes land is DOC-004's business and is tested there.
    """
    async for session in mock_get_session():
        yield ReportGenerator(db=session, vault=DocumentVault(backend=MemoryVault()))


@pytest.fixture(autouse=True)
def setup_overrides():
    # Setup dependency overrides before each test
    app.dependency_overrides[get_current_user] = mock_get_current_user
    app.dependency_overrides[get_session] = mock_get_session
    app.dependency_overrides[get_report_generator] = mock_get_report_generator
    yield
    # Cleanup overrides after each test
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_report_generator, None)


def test_reports_endpoints():
    with TestClient(app) as client:
        # 1. Test POST /api/v1/reports/generate (tax_summary)
        res = client.post("/api/v1/reports/generate", json={"report_type": "tax_summary"})
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["report_type"] == "tax_summary"
        
        # 2. Test POST /api/v1/reports/health-score
        res = client.post("/api/v1/reports/health-score", json={"include_breakdown": True})
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "overall_score" in data["result"]
        
        # 3. Test GET /api/v1/reports/list
        res = client.get("/api/v1/reports/list")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "reports" in data


def test_a_report_that_could_not_be_generated_is_not_a_200():
    """The failure the vault outage exposed.

    Storage was unreachable, the generator returned `{"success": False}`, and
    the endpoint passed that through with HTTP 200 and a null filename. Every
    client that checks the status code — which is the whole point of one —
    would have told the user their report was ready.
    """
    class FailingGenerator:
        async def generate_tax_summary_report(self, **_):
            return {"success": False, "error": "vault unreachable"}

    async def _failing():
        yield FailingGenerator()

    app.dependency_overrides[get_report_generator] = _failing
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            res = client.post(
                "/api/v1/reports/generate", json={"report_type": "tax_summary"},
            )
        assert res.status_code == 502
        # The reason is logged, never returned (DEM-008).
        assert "vault" not in res.text.lower()
    finally:
        app.dependency_overrides.pop(get_report_generator, None)


def test_notifications_endpoints():
    with TestClient(app) as client:
        # 1. Test POST /api/v1/notifications/preferences
        res = client.post("/api/v1/notifications/preferences", json={
            "channel": "email",
            "enabled": True,
            "frequency": "weekly",
            "preferred_time": "10:00:00"
        })
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["channel"] == "email"
        
        # 2. Test GET /api/v1/notifications/preferences
        res = client.get("/api/v1/notifications/preferences")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        
        # 3. Test GET /api/v1/notifications/history
        res = client.get("/api/v1/notifications/history")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "notifications" in data
