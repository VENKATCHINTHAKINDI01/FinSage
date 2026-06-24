"""
Compliance API Endpoints - Step 9
=================================

Hierarchical endpoints for Step 9 agents.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional, Dict, Any

from backend.db.postgres import get_session
from backend.security.dependencies import get_current_user
from backend.orchestrator.graph import get_orchestrator, db_session_var
try:
    from backend.db.orm_models_step9_10 import ComplianceReport, ITRFiling, TaxCalculation
except ImportError:
    from backend.db.orm_models import ComplianceReport, ITRFiling, TaxCalculation

router = APIRouter(prefix="/api/v1/compliance", tags=["compliance"])


class ComplianceReportRequest(BaseModel):
    """Request for compliance check"""
    conversation_id: Optional[str] = None


class ITRGuidanceRequest(BaseModel):
    """Request for ITR filing guidance"""
    conversation_id: Optional[str] = None


class TaxCalculationRequest(BaseModel):
    """Request for advanced tax calculation"""
    income_sources: Optional[Dict[str, Any]] = None
    deductions: Optional[Dict[str, Any]] = None
    capital_gains: Optional[Dict[str, Any]] = None
    losses: Optional[Dict[str, Any]] = None
    conversation_id: Optional[str] = None


# ===== ENDPOINT 1: Full Compliance Report =====

@router.post("/report")
async def get_compliance_report(
    request: ComplianceReportRequest,
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """
    Get comprehensive compliance assessment.
    
    Returns:
    • Compliance score (0-100)
    • Audit readiness status
    • Red flags (India-specific)
    • Missing documents
    • Risk level
    • Recommendations
    """
    
    orchestrator = get_orchestrator()
    if not orchestrator:
        raise HTTPException(status_code=503, detail="System not ready")
    
    token = db_session_var.set(session)
    
    try:
        # Get user context
        user_context = {
            "user_id": current_user.id,
            "email": current_user.email,
            "age": getattr(current_user, "age", 35),
            "annual_income": getattr(current_user, "annual_income", 0),
            "employment_type": getattr(current_user, "employment_type", "salaried"),
            "tds_paid": getattr(current_user, "tds_paid", 0),
            "deductions": getattr(current_user, "deductions", {}),
            "gst_registered": getattr(current_user, "gst_registered", False),
            "advance_tax_paid": getattr(current_user, "advance_tax_paid", 0)
        }
        
        # Run orchestration
        result = await orchestrator.orchestrate(
            user_query="What is my compliance status and audit readiness?",
            user_id=current_user.id,
            user_context=user_context,
            agents_to_invoke=["compliance_checker_agent"],
            conversation_id=request.conversation_id
        )
        
        # Extract result
        agent_result = result.get("agent_results", {}).get("compliance_checker_agent", {})
        
        # Handle AgentOutput object or dict
        res_data = {}
        if hasattr(agent_result, "result"):
            res_data = agent_result.result
        elif isinstance(agent_result, dict):
            res_data = agent_result.get("result", {})
            
        return {
            "success": True,
            "compliance_score": res_data.get("compliance_score"),
            "audit_ready": res_data.get("audit_ready"),
            "audit_readiness_status": res_data.get("audit_readiness_status"),
            "red_flags": res_data.get("red_flags"),
            "red_flag_count": res_data.get("red_flag_count"),
            "missing_documents": res_data.get("missing_documents"),
            "risk_level": res_data.get("risk_level"),
            "recommendations": res_data.get("recommendations"),
            "itr_deadline": res_data.get("itr_deadline"),
            "days_to_deadline": res_data.get("days_to_deadline")
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db_session_var.reset(token)


# ===== ENDPOINT 2: ITR Filing Guidance =====

@router.post("/filing")
async def get_itr_filing_guidance(
    request: ITRGuidanceRequest,
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """
    Get step-by-step ITR filing guidance.
    
    Returns:
    • Recommended ITR form (1, 2, 4, or 5)
    • Filing requirements
    • 12-step filing process
    • Common mistakes to avoid
    • TDS validation
    • Advance tax validation
    """
    
    orchestrator = get_orchestrator()
    if not orchestrator:
        raise HTTPException(status_code=503, detail="System not ready")
    
    token = db_session_var.set(session)
    
    try:
        user_context = {
            "user_id": current_user.id,
            "annual_income": getattr(current_user, "annual_income", 0),
            "employment_type": getattr(current_user, "employment_type", "salaried"),
            "has_capital_gains": getattr(current_user, "has_capital_gains", False),
            "tds_paid": getattr(current_user, "tds_paid", 0),
            "calculated_tax": getattr(current_user, "calculated_tax", 0),
            "form_16_tds": getattr(current_user, "form_16_tds", 0),
            "advance_tax_paid": getattr(current_user, "advance_tax_paid", 0)
        }
        
        result = await orchestrator.orchestrate(
            user_query="How do I file my ITR?",
            user_id=current_user.id,
            user_context=user_context,
            agents_to_invoke=["itr_helper_agent"],
            conversation_id=request.conversation_id
        )
        
        agent_result = result.get("agent_results", {}).get("itr_helper_agent", {})
        
        # Handle AgentOutput object or dict
        res_data = {}
        if hasattr(agent_result, "result"):
            res_data = agent_result.result
        elif isinstance(agent_result, dict):
            res_data = agent_result.get("result", {})
        
        return {
            "success": True,
            "recommended_form": res_data.get("recommended_form"),
            "form_details": res_data.get("form_details"),
            "financial_year": res_data.get("financial_year"),
            "filing_requirements": res_data.get("filing_requirements"),
            "step_by_step_guide": res_data.get("step_by_step_guide"),
            "estimated_time": res_data.get("estimated_time"),
            "tds_validation": res_data.get("tds_validation"),
            "advance_tax_validation": res_data.get("advance_tax_validation"),
            "important_dates": res_data.get("important_dates"),
            "filing_checklist": res_data.get("filing_checklist"),
            "days_to_deadline": res_data.get("days_to_deadline"),
            "common_mistakes": res_data.get("common_mistakes"),
            "next_actions": res_data.get("next_actions"),
            "portal_url": res_data.get("portal_url")
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db_session_var.reset(token)


# ===== ENDPOINT 3: Advanced Tax Calculation =====

@router.post("/calculator")
async def calculate_advanced_tax(
    request: TaxCalculationRequest,
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """
    Calculate complex tax scenarios.
    
    Returns:
    • Tax breakdown by income type
    • Deduction details
    • Taxable income
    • Tax liability (Income Tax + Surcharge + Cess)
    • Effective tax rate
    • Loss set-off details
    • GST impact
    • Refund or balance due
    • Optimization suggestions
    """
    
    orchestrator = get_orchestrator()
    if not orchestrator:
        raise HTTPException(status_code=503, detail="System not ready")
    
    token = db_session_var.set(session)
    
    try:
        user_context = {
            "user_id": current_user.id,
            "annual_income": getattr(current_user, "annual_income", 0),
            "age": getattr(current_user, "age", 35),
            "employment_type": getattr(current_user, "employment_type", "salaried"),
            "deductions": request.deductions or getattr(current_user, "deductions", {}),
            "long_term_gains": (request.capital_gains or {}).get("ltcg", 0),
            "short_term_gains": (request.capital_gains or {}).get("stcg", 0),
            "losses": request.losses or {},
            "tds_paid": getattr(current_user, "tds_paid", 0),
            "advance_tax_paid": getattr(current_user, "advance_tax_paid", 0),
            "turnover": getattr(current_user, "turnover", 0),
            "gst_registered": getattr(current_user, "gst_registered", False)
        }
        
        result = await orchestrator.orchestrate(
            user_query="Calculate my comprehensive tax liability",
            user_id=current_user.id,
            user_context=user_context,
            agents_to_invoke=["advanced_calculator_agent"],
            conversation_id=request.conversation_id
        )
        
        agent_result = result.get("agent_results", {}).get("advanced_calculator_agent", {})
        
        # Handle AgentOutput object or dict
        res_data = {}
        if hasattr(agent_result, "result"):
            res_data = agent_result.result
        elif isinstance(agent_result, dict):
            res_data = agent_result.get("result", {})
        
        return {
            "success": True,
            "financial_year": res_data.get("financial_year"),
            "gross_income": res_data.get("gross_income"),
            "income_breakdown": res_data.get("income_breakdown"),
            "total_deductions": res_data.get("deductions", {}).get("total_claimed"),
            "taxable_income": res_data.get("taxable_income"),
            "tax_calculation": res_data.get("tax_calculation"),
            "effective_tax_rate": res_data.get("effective_tax_rate"),
            "loss_setoff": res_data.get("loss_setoff"),
            "gst_details": res_data.get("gst_details"),
            "tds_credit": res_data.get("tds_credit"),
            "refund_or_balance": res_data.get("refund_or_balance"),
            "optimization_suggestions": res_data.get("optimization_suggestions"),
            "potential_savings": res_data.get("potential_savings"),
            "summary": res_data.get("summary")
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db_session_var.reset(token)


# ===== ENDPOINT 4: Audit History =====

@router.get("/audit-history")
async def get_audit_history(
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """Get user's compliance & audit history"""
    
    from sqlalchemy import select
    
    try:
        result = await session.execute(
            select(ComplianceReport)
            .where(ComplianceReport.user_id == current_user.id)
            .order_by(ComplianceReport.report_date.desc())
            .limit(5)
        )
        reports = result.scalars().all()
        
        history = [
            {
                "date": r.report_date.isoformat(),
                "compliance_score": r.compliance_score,
                "audit_ready": r.audit_readiness,
                "risk_level": r.risk_level,
                "red_flag_count": len(r.red_flags) if r.red_flags else 0
            }
            for r in reports
        ]
        
        return {
            "success": True,
            "history": history,
            "total_reports": len(history)
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===== ENDPOINT 5: ITR Filing Status =====

@router.get("/itr-status")
async def get_itr_filing_status(
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """Get ITR filing status for current FY"""
    
    from sqlalchemy import select
    
    try:
        result = await session.execute(
            select(ITRFiling)
            .where(
                ITRFiling.user_id == current_user.id,
                ITRFiling.financial_year == "2024-25"
            )
        )
        itr = result.scalar_one_or_none()
        
        if itr:
            return {
                "success": True,
                "itr_form": itr.itr_form,
                "status": itr.status,
                "filing_date": itr.filing_date.isoformat() if itr.filing_date else None,
                "verification_date": itr.verification_date.isoformat() if itr.verification_date else None
            }
        else:
            return {
                "success": True,
                "message": "No ITR filed for FY 2024-25"
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
