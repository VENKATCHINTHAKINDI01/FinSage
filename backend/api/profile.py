"""
Profile API Endpoints
=====================

Handles retrieving and updating detailed user financial profiles.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging

from backend.db.postgres import get_session
from backend.security.dependencies import get_current_user
from backend.db.orm_models import FinancialProfile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/profile", tags=["profile"])


class ProfileUpdateRequest(BaseModel):
    """Detailed profile request structure matching frontend Zustand store state."""
    dob: Optional[str] = ""
    pan: Optional[str] = ""
    aadhaarLast4: Optional[str] = ""
    state: Optional[str] = ""
    residentialStatus: Optional[str] = "resident"
    profession: Optional[str] = ""
    employerName: Optional[str] = ""
    businessType: Optional[str] = ""
    
    # Income fields
    salaryCtc: Optional[float] = 0.0
    salaryInHand: Optional[float] = 0.0
    businessIncome: Optional[float] = 0.0
    freelanceIncome: Optional[float] = 0.0
    rentalIncome: Optional[float] = 0.0
    capitalGainsStcg: Optional[float] = 0.0
    capitalGainsLtcg: Optional[float] = 0.0
    otherIncome: Optional[float] = 0.0
    dividendIncome: Optional[float] = 0.0
    
    # Investments (80C)
    ppf: Optional[float] = 0.0
    elss: Optional[float] = 0.0
    lic: Optional[float] = 0.0
    ulip: Optional[float] = 0.0
    fd5yr: Optional[float] = 0.0
    sukanyaSamriddhi: Optional[float] = 0.0
    nsc: Optional[float] = 0.0
    homeLoanPrincipal: Optional[float] = 0.0
    
    # NPS
    npsEmployee: Optional[float] = 0.0
    npsEmployer: Optional[float] = 0.0
    
    # Deductions
    healthInsuranceSelf: Optional[float] = 0.0
    healthInsuranceParents: Optional[float] = 0.0
    eduLoanInterest: Optional[float] = 0.0
    homeLoanInterest: Optional[float] = 0.0
    homeLoanInterest80EEA: Optional[float] = 0.0
    evLoanInterest: Optional[float] = 0.0
    savingsBankInterest: Optional[float] = 0.0
    donationsU80G: Optional[float] = 0.0
    hra: Optional[float] = 0.0
    lta: Optional[float] = 0.0
    
    # Assets
    hasProperty: Optional[bool] = False
    propertyType: Optional[str] = ""
    propertyPurchaseCost: Optional[float] = 0.0
    propertyPurchaseYear: Optional[float] = 0.0
    propertyLoanOutstanding: Optional[float] = 0.0
    hasVehicle: Optional[bool] = False
    vehicleType: Optional[str] = ""
    vehicleUsage: Optional[str] = ""
    vehiclePurchaseValue: Optional[float] = 0.0
    goldValue: Optional[float] = 0.0
    equityPortfolioValue: Optional[float] = 0.0
    mutualFundValue: Optional[float] = 0.0
    
    # Tax Preferences
    taxRegime: Optional[str] = "new"
    isHUF: Optional[bool] = False
    filingStatus: Optional[str] = "individual"
    
    # Family
    maritalStatus: Optional[str] = ""
    dependents: Optional[int] = 0
    seniorParents: Optional[bool] = False
    superSeniorParents: Optional[bool] = False


@router.get("")
async def get_profile(
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """Get the current authenticated user's financial profile."""
    try:
        logger.info(f"Fetching profile for user: {current_user.id}")
        
        # Query existing profile
        result = await session.execute(
            select(FinancialProfile).where(FinancialProfile.user_id == current_user.id)
        )
        profile_rec = result.scalar_one_or_none()
        
        if not profile_rec:
            return {
                "success": True,
                "profile": None
            }
            
        return {
            "success": True,
            "profile": profile_rec.profile_data or {}
        }
        
    except Exception as e:
        logger.error(f"Error fetching profile: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def update_profile(
    payload: ProfileUpdateRequest,
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """Create or update user's financial profile."""
    try:
        logger.info(f"Saving profile for user: {current_user.id}")
        
        # Query existing profile
        result = await session.execute(
            select(FinancialProfile).where(FinancialProfile.user_id == current_user.id)
        )
        profile_rec = result.scalar_one_or_none()
        
        # Calculate derived relational columns
        gross_income = (
            (payload.salaryCtc if payload.profession == "salaried" else 0) +
            payload.businessIncome +
            payload.freelanceIncome +
            payload.rentalIncome +
            payload.capitalGainsStcg +
            payload.capitalGainsLtcg +
            payload.otherIncome +
            payload.dividendIncome
        )
        
        total_investments = (
            payload.ppf +
            payload.elss +
            payload.lic +
            payload.ulip +
            payload.fd5yr +
            payload.sukanyaSamriddhi +
            payload.nsc +
            payload.homeLoanPrincipal
        )
        
        # Map employment type to DB supported categories (max 20 chars)
        emp_type = payload.profession if payload.profession in ["individual", "freelancer", "salaried", "business", "retired"] else "individual"
        
        # Construct dictionary representation
        profile_dict = payload.model_dump()
        
        if profile_rec:
            # Update existing record
            profile_rec.annual_income = gross_income
            profile_rec.investment_amount = total_investments
            profile_rec.employment_type = emp_type
            profile_rec.profile_data = profile_dict
        else:
            # Create new record
            profile_rec = FinancialProfile(
                user_id=current_user.id,
                annual_income=gross_income,
                monthly_expenses=0,
                investment_amount=total_investments,
                employment_type=emp_type,
                financial_goal="Optimized financial savings and tax reduction",
                profile_data=profile_dict
            )
            session.add(profile_rec)
            
        await session.commit()
        await session.refresh(profile_rec)
        
        logger.info(f"Successfully saved profile for user: {current_user.id}")
        
        return {
            "success": True,
            "profile": profile_rec.profile_data
        }
        
    except Exception as e:
        logger.error(f"Error saving profile: {e}", exc_info=True)
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
