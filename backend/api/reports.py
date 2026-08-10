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
        from sqlalchemy import select
        from backend.db.orm_models import FinancialProfile, ComplianceReport, RedFlagLog
        
        report_gen = ReportGenerator(db=session)
        
        # Load user profile for data
        result_profile = await session.execute(
            select(FinancialProfile).where(FinancialProfile.user_id == current_user.id)
        )
        profile_rec = result_profile.scalar_one_or_none()
        profile_data = profile_rec.profile_data if (profile_rec and profile_rec.profile_data) else {}
        
        # Calculations (Gross Income & Deductions)
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
        
        total_deductions = total_80c + total_80ccd + total_80d + sec24b + float(profile_data.get("eduLoanInterest", 0.0)) + float(profile_data.get("evLoanInterest", 0.0)) + min(10000.0, float(profile_data.get("savingsBankInterest", 0.0)))
        
        taxable_income = max(0.0, gross_income - total_deductions)
        regime = profile_data.get("taxRegime", "new")
        
        tax = 0.0
        if regime == "new":
            slabs = [
                (0, 300000, 0.0),
                (300000, 700000, 0.05),
                (700000, 1000000, 0.10),
                (1000000, 1200000, 0.15),
                (1200000, 1500000, 0.20),
                (1500000, float("inf"), 0.30)
            ]
            for s_min, s_max, s_rate in slabs:
                if taxable_income <= s_min:
                    break
                taxable_in_slab = min(taxable_income, s_max) - s_min
                tax += taxable_in_slab * s_rate
            if taxable_income <= 700000:
                tax = 0.0
        else:
            slabs = [
                (0, 250000, 0.0),
                (250000, 500000, 0.05),
                (500000, 1000000, 0.20),
                (1000000, float("inf"), 0.30)
            ]
            for s_min, s_max, s_rate in slabs:
                if taxable_income <= s_min:
                    break
                taxable_in_slab = min(taxable_income, s_max) - s_min
                tax += taxable_in_slab * s_rate
            if taxable_income <= 500000:
                tax = 0.0
                
        cess = tax * 0.04
        total_tax = tax + cess
        effective_tax_rate = (total_tax / gross_income * 100.0) if gross_income > 0 else 0.0
        
        # Latest compliance report
        res_comp = await session.execute(
            select(ComplianceReport).where(ComplianceReport.user_id == current_user.id).order_by(ComplianceReport.report_date.desc()).limit(1)
        )
        comp_rec = res_comp.scalars().first()
        compliance_score = comp_rec.compliance_score if comp_rec else 80
        audit_ready = comp_rec.audit_readiness if comp_rec else True
        risk_level = comp_rec.risk_level if comp_rec else "Low Risk"
        comp_recs = comp_rec.recommendations if comp_rec else ["Maintain structured invoices"]
        
        # Red flags
        res_flags = await session.execute(
            select(RedFlagLog).where(RedFlagLog.user_id == current_user.id).where(RedFlagLog.resolved == False)
        )
        red_flags_list = [{"flag": f.flag_name, "severity": f.severity} for f in res_flags.scalars().all()]
        if not red_flags_list:
            red_flags_list = [{"flag": "No active compliance flags", "severity": "Low"}]
        
        if request.report_type == "compliance":
            compliance_data = {
                "compliance_score": compliance_score,
                "audit_ready": audit_ready,
                "risk_level": risk_level,
                "red_flags": red_flags_list,
                "recommendations": comp_recs
            }
            result = await report_gen.generate_compliance_report(
                user_id=current_user.id,
                compliance_data=compliance_data
            )
        
        elif request.report_type == "financial_health":
            # Dynamic calculation via scorer
            scorer = FinancialHealthScorer(db=session)
            health_data = {
                "gross_income": gross_income,
                "total_deductions": total_deductions,
                "effective_tax_rate": effective_tax_rate,
                "compliance_score": compliance_score,
                "red_flags": len(red_flags_list) if red_flags_list and red_flags_list[0]["flag"] != "No active compliance flags" else 0,
                "missing_documents": 0,
                "audit_ready": audit_ready,
                "life_insurance": lic > 0 or ulip > 0,
                "mutual_funds": elss > 0 or float(profile_data.get("mutualFundValue", 0)) > 0,
                "ppf": ppf > 0,
                "nsc": nsc > 0,
                "health_insurance": health_self > 0 or health_parents > 0,
                "nps": nps_emp > 0,
                "fixed_deposits": fd5yr > 0,
                "savings_account": float(profile_data.get("savingsBankInterest", 0)) > 0
            }
            health_res = await scorer.calculate_health_score(current_user.id, health_data)
            overall_score = health_res["result"]["overall_score"] if health_res.get("success") else 75
            
            result = await report_gen.generate_financial_health_report(
                user_id=current_user.id,
                health_score=overall_score,
                health_data={
                    "tax_efficiency_score": health_res["result"]["breakdown"]["tax_efficiency"]["score"] if health_res.get("success") else 80,
                    "deduction_optimization_score": health_res["result"]["breakdown"]["deduction_optimization"]["score"] if health_res.get("success") else 75,
                    "savings_potential_score": health_res["result"]["breakdown"]["savings_potential"]["score"] if health_res.get("success") else 70,
                    "compliance_status_score": health_res["result"]["breakdown"]["compliance_status"]["score"] if health_res.get("success") else 85,
                    "investment_diversity_score": health_res["result"]["breakdown"]["investment_diversity"]["score"] if health_res.get("success") else 78
                }
            )
        
        elif request.report_type == "tax_summary":
            tax_data = {
                "gross_income": gross_income,
                "total_deductions": total_deductions,
                "taxable_income": taxable_income,
                "total_tax_liability": total_tax,
                "effective_rate": effective_tax_rate
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
        raise  # DEM-008: handled globally; str(e) must not reach the client


# ===== ENDPOINT 2: Get Health Score =====

@router.post("/health-score")
async def get_health_score(
    request: HealthScoreRequest,
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """
    Get financial health score.
    """
    try:
        from sqlalchemy import select
        from backend.db.orm_models import FinancialProfile, ComplianceReport, RedFlagLog
        
        # Load user profile
        result_profile = await session.execute(
            select(FinancialProfile).where(FinancialProfile.user_id == current_user.id)
        )
        profile_rec = result_profile.scalar_one_or_none()
        
        if not profile_rec:
            # Starting fresh user defaults (uninitialized)
            return {
                "success": True,
                "result": {
                    "overall_score": 0,
                    "health_status": {
                        "level": "Uninitialized",
                        "emoji": "⚪",
                        "message": "Complete your financial profile to calculate your score.",
                        "color": "#9CA3AF"
                    },
                    "breakdown": {
                        "tax_efficiency": {"score": 0, "weight": "20%", "description": "How efficiently you manage tax liability"},
                        "deduction_optimization": {"score": 0, "weight": "20%", "description": "How well you utilize available deductions"},
                        "savings_potential": {"score": 0, "weight": "20%", "description": "Potential for additional tax savings"},
                        "compliance_status": {"score": 0, "weight": "20%", "description": "Your tax compliance readiness"},
                        "investment_diversity": {"score": 0, "weight": "20%", "description": "Diversification of investments for tax benefits"}
                    },
                    "recommendations": ["Fill your financial profile to get tax optimization tips."],
                    "action_items": ["Go to Profile page and complete Step 1 - Step 5"]
                }
            }
            
        profile_data = profile_rec.profile_data or {}
        
        # Calculations (Gross Income & Deductions)
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
        
        total_deductions = total_80c + total_80ccd + total_80d + sec24b + float(profile_data.get("eduLoanInterest", 0.0)) + float(profile_data.get("evLoanInterest", 0.0)) + min(10000.0, float(profile_data.get("savingsBankInterest", 0.0)))
        
        taxable_income = max(0.0, gross_income - total_deductions)
        regime = profile_data.get("taxRegime", "new")
        
        tax = 0.0
        if regime == "new":
            slabs = [
                (0, 300000, 0.0),
                (300000, 700000, 0.05),
                (700000, 1000000, 0.10),
                (1000000, 1200000, 0.15),
                (1200000, 1500000, 0.20),
                (1500000, float("inf"), 0.30)
            ]
            for s_min, s_max, s_rate in slabs:
                if taxable_income <= s_min:
                    break
                taxable_in_slab = min(taxable_income, s_max) - s_min
                tax += taxable_in_slab * s_rate
            if taxable_income <= 700000:
                tax = 0.0
        else:
            slabs = [
                (0, 250000, 0.0),
                (250000, 500000, 0.05),
                (500000, 1000000, 0.20),
                (1000000, float("inf"), 0.30)
            ]
            for s_min, s_max, s_rate in slabs:
                if taxable_income <= s_min:
                    break
                taxable_in_slab = min(taxable_income, s_max) - s_min
                tax += taxable_in_slab * s_rate
            if taxable_income <= 500000:
                tax = 0.0
                
        cess = tax * 0.04
        total_tax = tax + cess
        effective_tax_rate = (total_tax / gross_income * 100.0) if gross_income > 0 else 0.0
        
        res_comp = await session.execute(
            select(ComplianceReport).where(ComplianceReport.user_id == current_user.id).order_by(ComplianceReport.report_date.desc()).limit(1)
        )
        comp_rec = res_comp.scalars().first()
        compliance_score = comp_rec.compliance_score if comp_rec else 80
        audit_ready = comp_rec.audit_readiness if comp_rec else True
        
        res_flags = await session.execute(
            select(RedFlagLog).where(RedFlagLog.user_id == current_user.id).where(RedFlagLog.resolved == False)
        )
        red_flags_count = len(res_flags.scalars().all())
        
        scorer = FinancialHealthScorer(db=session)
        financial_data = {
            "gross_income": gross_income,
            "total_deductions": total_deductions,
            "effective_tax_rate": effective_tax_rate,
            "compliance_score": compliance_score,
            "red_flags": red_flags_count,
            "missing_documents": 0,
            "audit_ready": audit_ready,
            "life_insurance": lic > 0 or ulip > 0,
            "mutual_funds": elss > 0 or float(profile_data.get("mutualFundValue", 0)) > 0,
            "ppf": ppf > 0,
            "nsc": nsc > 0,
            "health_insurance": health_self > 0 or health_parents > 0,
            "nps": nps_emp > 0,
            "fixed_deposits": fd5yr > 0,
            "savings_account": float(profile_data.get("savingsBankInterest", 0)) > 0
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
        raise  # DEM-008: handled globally; str(e) must not reach the client


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
        raise  # DEM-008: handled globally; str(e) must not reach the client
