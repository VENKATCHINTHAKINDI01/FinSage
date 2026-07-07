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


async def fetch_user_context(user_id: str, email: str, session: AsyncSession) -> Dict[str, Any]:
    from sqlalchemy import select
    from backend.db.orm_models import FinancialProfile
    
    result_profile = await session.execute(
        select(FinancialProfile).where(FinancialProfile.user_id == user_id)
    )
    profile_rec = result_profile.scalar_one_or_none()
    profile_data = profile_rec.profile_data if (profile_rec and profile_rec.profile_data) else {}
    
    # Calculate gross income
    salary_ctc = float(profile_data.get("salaryCtc", 0.0))
    profession = profile_data.get("profession", "")
    business_inc = float(profile_data.get("businessIncome", 0.0))
    freelance_inc = float(profile_data.get("freelanceIncome", 0.0))
    rental_inc = float(profile_data.get("rentalIncome", 0.0))
    cg_stcg = float(profile_data.get("capitalGainsStcg", 0.0))
    cg_ltcg = float(profile_data.get("capitalGainsLtcg", 0.0))
    other_inc = float(profile_data.get("otherIncome", 0.0))
    div_inc = float(profile_data.get("dividendIncome", 0.0))
    
    gross_income = (
        (salary_ctc if profession == "salaried" else 0.0) +
        business_inc +
        freelance_inc +
        rental_inc +
        cg_stcg +
        cg_ltcg +
        other_inc +
        div_inc
    )
    
    # Deductions
    ppf = float(profile_data.get("ppf", 0.0))
    elss = float(profile_data.get("elss", 0.0))
    lic = float(profile_data.get("lic", 0.0))
    ulip = float(profile_data.get("ulip", 0.0))
    fd5yr = float(profile_data.get("fd5yr", 0.0))
    nsc = float(profile_data.get("nsc", 0.0))
    sukanya = float(profile_data.get("sukanyaSamriddhi", 0.0))
    hl_principal = float(profile_data.get("homeLoanPrincipal", 0.0))
    
    total_80c = min(150000.0, ppf + elss + lic + ulip + fd5yr + nsc + sukanya + hl_principal)
    nps_emp = float(profile_data.get("npsEmployee", 0.0))
    total_80ccd = min(50000.0, nps_emp)
    health_self = float(profile_data.get("healthInsuranceSelf", 0.0))
    health_parents = float(profile_data.get("healthInsuranceParents", 0.0))
    total_80d = min(25000.0, health_self) + min(50000.0, health_parents)
    hl_interest = float(profile_data.get("homeLoanInterest", 0.0))
    sec24b = min(200000.0, hl_interest)
    
    deductions_dict = {
        "80c": total_80c,
        "80d": total_80d,
        "nps": total_80ccd,
        "home_loan_interest": sec24b,
        "ev_loan_interest": float(profile_data.get("evLoanInterest", 0.0)),
        "education_loan_interest": float(profile_data.get("eduLoanInterest", 0.0)),
        "savings_interest": float(profile_data.get("savingsBankInterest", 0.0)),
        "donations": float(profile_data.get("donationsU80G", 0.0)),
        "hra": float(profile_data.get("hra", 0.0)),
        "lta": float(profile_data.get("lta", 0.0))
    }
    
    return {
        "user_id": user_id,
        "email": email,
        "age": profile_data.get("age") or 35,
        "annual_income": gross_income,
        "employment_type": profession or "salaried",
        "tds_paid": float(profile_data.get("tds_paid", 0.0)),
        "deductions": deductions_dict,
        "gst_registered": profession in ["business_owner", "professional", "freelancer"],
        "advance_tax_paid": float(profile_data.get("advance_tax_paid", 0.0)),
        "has_capital_gains": cg_stcg > 0 or cg_ltcg > 0,
        "calculated_tax": 0.0,
        "form_16_tds": float(profile_data.get("form_16_tds", 0.0)),
        "turnover": float(profile_data.get("turnover", 0.0)),
        "long_term_gains": cg_ltcg,
        "short_term_gains": cg_stcg,
        "losses": profile_data.get("losses") or {}
    }


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
        # Get user context dynamically from database profile
        db_context = await fetch_user_context(current_user.id, current_user.email, session)
        
        user_context = {
            "user_id": current_user.id,
            "annual_income": db_context.get("annual_income", 0.0),
            "age": db_context.get("age", 35),
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
