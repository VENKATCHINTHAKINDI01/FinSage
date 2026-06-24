import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from backend.services.report_generator import ReportGenerator

@pytest.mark.asyncio
async def test_generate_compliance_report():
    mock_db = MagicMock(spec=AsyncSession)
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()
    generator = ReportGenerator(db=mock_db)
    
    compliance_data = {
        "compliance_score": 85,
        "audit_ready": True,
        "risk_level": "🟢 Low Risk",
        "red_flags": [{"flag": "None"}],
        "recommendations": ["File on time"]
    }
    
    result = await generator.generate_compliance_report("user-123", compliance_data)
    assert result["success"] is True
    assert result["report_type"] == "compliance"
    assert "compliance_report_user-123_" in result["filename"]
    assert mock_db.add.called
    assert mock_db.commit.called

@pytest.mark.asyncio
async def test_generate_financial_health_report():
    mock_db = MagicMock(spec=AsyncSession)
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()
    generator = ReportGenerator(db=mock_db)
    
    health_data = {
        "tax_efficiency_score": 80,
        "deduction_optimization_score": 90,
        "savings_potential_score": 75,
        "compliance_status_score": 95,
        "investment_diversity_score": 85
    }
    
    result = await generator.generate_financial_health_report("user-123", 85, health_data)
    assert result["success"] is True
    assert result["report_type"] == "financial_health"
    assert mock_db.add.called
    assert mock_db.commit.called

@pytest.mark.asyncio
async def test_generate_tax_summary_report():
    mock_db = MagicMock(spec=AsyncSession)
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()
    generator = ReportGenerator(db=mock_db)
    
    tax_data = {
        "gross_income": 1200000,
        "total_deductions": 150000,
        "taxable_income": 1050000,
        "total_tax_liability": 115000,
        "effective_rate": 9.58
    }
    
    result = await generator.generate_tax_summary_report("user-123", tax_data)
    assert result["success"] is True
    assert result["report_type"] == "tax_summary"
    assert mock_db.add.called
    assert mock_db.commit.called

@pytest.mark.asyncio
async def test_get_report_list():
    mock_db = MagicMock(spec=AsyncSession)
    mock_report = MagicMock()
    mock_report.id = "rep-123"
    mock_report.report_type = "compliance"
    mock_report.title = "Compliance Assessment Report"
    mock_report.generated_at.isoformat.return_value = "2026-06-22T00:00:00"
    mock_report.file_size = 1024
    mock_report.download_count = 1
    
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_report]
    mock_db.execute = AsyncMock(return_value=mock_result)
    
    generator = ReportGenerator(db=mock_db)
    reports = await generator.get_report_list("user-123")
    assert len(reports) == 1
    assert reports[0]["id"] == "rep-123"
    assert reports[0]["type"] == "compliance"
