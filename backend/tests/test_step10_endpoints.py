import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from backend.main import app
from backend.security.dependencies import get_current_user
from backend.db.postgres import get_session


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


@pytest.fixture(autouse=True)
def setup_overrides():
    # Setup dependency overrides before each test
    app.dependency_overrides[get_current_user] = mock_get_current_user
    app.dependency_overrides[get_session] = mock_get_session
    yield
    # Cleanup overrides after each test
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_session, None)


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
