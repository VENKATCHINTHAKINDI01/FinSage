"""
Reports API Endpoints - Step 10
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from backend.security.dependencies import get_current_user
from backend.db.postgres import get_session
from backend.services.report_generator import ReportGenerator
from backend.services.health_scorer import FinancialHealthScorer

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


class GenerateReportRequest(BaseModel):
    """Request to generate report"""
    report_type: str  # compliance, financial_health, tax_summary
    conversation_id: Optional[str] = None


class HealthScoreRequest(BaseModel):
    """Request for health score"""
    include_breakdown: bool = True


# ===== ENDPOINT 1: Generate Report =====

@router.post("/generate")
async def generate_report(
    request: GenerateReportRequest,
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """
    Generate PDF report.
    
    Report Types:
    • compliance - Compliance assessment
    • financial_health - Health score + factors
    • tax_summary - Income, tax, deductions
    """
    try:
        report_gen = ReportGenerator(db=session)
        
        if request.report_type == "compliance":
            # Get compliance data
            compliance_data = {
                "compliance_score": 85,
                "audit_ready": True,
                "risk_level": "Low Risk",
                "red_flags": [{"flag": "Sample", "severity": "Low"}],
                "recommendations": ["Sample recommendation"]
            }
            
            result = await report_gen.generate_compliance_report(
                user_id=current_user.id,
                compliance_data=compliance_data
            )
        
        elif request.report_type == "financial_health":
            health_data = {
                "tax_efficiency_score": 80,
                "deduction_optimization_score": 75,
                "savings_potential_score": 70,
                "compliance_status_score": 85,
                "investment_diversity_score": 78
            }
            
            result = await report_gen.generate_financial_health_report(
                user_id=current_user.id,
                health_score=81,
                health_data=health_data
            )
        
        elif request.report_type == "tax_summary":
            tax_data = {
                "gross_income": 5000000,
                "total_deductions": 300000,
                "taxable_income": 4700000,
                "total_tax_liability": 940000,
                "effective_rate": 18.8
            }
            
            result = await report_gen.generate_tax_summary_report(
                user_id=current_user.id,
                tax_data=tax_data
            )
        
        else:
            raise HTTPException(status_code=400, detail="Invalid report type")
        
        return {
            "success": result.get("success"),
            "report_type": result.get("report_type"),
            "filename": result.get("filename"),
            "generated_at": result.get("generated_at")
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===== ENDPOINT 2: Get Health Score =====

@router.post("/health-score")
async def get_health_score(
    request: HealthScoreRequest,
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """
    Get financial health score.
    
    Returns:
    • Overall score (0-100)
    • 5 factors breakdown
    • Recommendations
    • Trend vs last month
    """
    try:
        scorer = FinancialHealthScorer(db=session)
        
        financial_data = {
            "gross_income": 5000000,
            "total_deductions": 300000,
            "effective_tax_rate": 18.8,
            "compliance_score": 85,
            "red_flags": 2,
            "missing_documents": 0,
            "audit_ready": True,
            "life_insurance": True,
            "mutual_funds": True,
            "ppf": True,
            "nsc": False,
            "health_insurance": True,
            "nps": False,
            "fixed_deposits": True,
            "savings_account": True
        }
        
        result = await scorer.calculate_health_score(
            user_id=current_user.id,
            financial_data=financial_data
        )
        
        if request.include_breakdown:
            return result
        else:
            return {
                "success": True,
                "overall_score": result["result"]["overall_score"],
                "health_status": result["result"]["health_status"]
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===== ENDPOINT 3: Get Reports List =====

@router.get("/list")
async def get_reports_list(
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """Get user's generated reports"""
    try:
        report_gen = ReportGenerator(db=session)
        reports = await report_gen.get_report_list(current_user.id)
        
        return {
            "success": True,
            "total_reports": len(reports),
            "reports": reports
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
