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
from backend.services.user_context import fetch_user_context
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
        # Get user context dynamically from database profile
        user_context = await fetch_user_context(current_user.id, current_user.email, session)
        
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
            "document_completeness": (res_data.get("document_status") or {}).get("completeness"),
            "risk_level": res_data.get("risk_level"),
            "recommendations": res_data.get("recommendations"),
            "itr_deadline": res_data.get("itr_deadline"),
            "days_to_deadline": res_data.get("days_to_deadline")
        }
    
    except Exception as e:
        raise  # DEM-008: handled globally; str(e) must not reach the client
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
        # Get user context dynamically from database profile
        user_context = await fetch_user_context(current_user.id, current_user.email, session)
        
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
        raise  # DEM-008: handled globally; str(e) must not reach the client
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
        # Get user context dynamically from database profile
        db_context = await fetch_user_context(current_user.id, current_user.email, session)
        
        user_context = {
            "user_id": current_user.id,
            "annual_income": db_context.get("annual_income", 0.0),
            "age": db_context.get("age", 35),
            "tax_regime": db_context.get("tax_regime", "new"),
            "employment_type": db_context.get("employment_type", "salaried"),
            "deductions": request.deductions or db_context.get("deductions", {}),
            "long_term_gains": (request.capital_gains or {}).get("ltcg") or db_context.get("long_term_gains", 0.0),
            "short_term_gains": (request.capital_gains or {}).get("stcg") or db_context.get("short_term_gains", 0.0),
            "losses": request.losses or db_context.get("losses", {}),
            "tds_paid": db_context.get("tds_paid", 0.0),
            "advance_tax_paid": db_context.get("advance_tax_paid", 0.0),
            "turnover": db_context.get("turnover", 0.0),
            "gst_registered": db_context.get("gst_registered", False)
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
        raise  # DEM-008: handled globally; str(e) must not reach the client
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
        raise  # DEM-008: handled globally; str(e) must not reach the client


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
        raise  # DEM-008: handled globally; str(e) must not reach the client
