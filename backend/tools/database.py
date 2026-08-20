"""
Database Integration Tools
===========================

Tools for agents to interact with database:
- Read user financial profiles
- Save analysis results
- Store recommendations
- Retrieve analysis history
"""

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================================
# DATA MODELS
# ============================================================================

class AnalysisType(str, Enum):
    """Types of analysis that can be saved."""
    INCOME_ANALYSIS = "income_analysis"
    DEDUCTION_ANALYSIS = "deduction_analysis"
    TAX_OPTIMIZATION = "tax_optimization"
    ELIGIBILITY_CHECK = "eligibility_check"
    REFUND_PROJECTION = "refund_projection"
    COMPREHENSIVE_TAX_PLAN = "comprehensive_tax_plan"


# ============================================================================
# USER FINANCIAL DATA TOOL
# ============================================================================

class UserFinancialDataTool:
    """Access user's financial profile from database."""

    def __init__(self, db_session):
        """
        Initialize with database session.
        
        Args:
            db_session: SQLAlchemy async session
        """
        self.db = db_session
        self.logger = logging.getLogger("tool.user_data")

    async def get_user_profile(self, user_id: str) -> dict[str, Any]:
        """
        Get complete user financial profile.
        """
        try:
            from sqlalchemy import select

            from backend.db.orm_models import FinancialProfile, User

            # Fetch user
            stmt_user = select(User).where(User.id == user_id)
            res_user = await self.db.execute(stmt_user)
            user_rec = res_user.scalar_one_or_none()
            email = user_rec.email if user_rec else "user@example.com"
            full_name = user_rec.full_name if user_rec else "User"

            # Fetch profile
            stmt_profile = select(FinancialProfile).where(FinancialProfile.user_id == user_id)
            res_profile = await self.db.execute(stmt_profile)
            profile_rec = res_profile.scalar_one_or_none()

            profile_data = profile_rec.profile_data if (profile_rec and profile_rec.profile_data) else {}

            annual_income = float(profile_rec.annual_income) if profile_rec else 0.0
            employment_type = profile_rec.employment_type if profile_rec else "individual"

            return {
                "success": True,
                "result": {
                    "user_id": user_id,
                    "email": email,
                    "full_name": full_name,
                    "basic_info": {
                        "age": profile_data.get("age") or 35,
                        "category": profile_data.get("filingStatus") or "individual",
                        "employment_type": employment_type
                    },
                    "financial_profile": {
                        "annual_income": annual_income,
                        "employment_income": float(profile_data.get("salaryCtc", annual_income)),
                        "other_income": float(profile_data.get("otherIncome", 0.0)),
                        "investments": {
                            "elss": float(profile_data.get("elss", 0.0)),
                            "ppf": float(profile_data.get("ppf", 0.0)),
                            "nps": float(profile_data.get("npsEmployee", 0.0)),
                            "mutual_funds": float(profile_data.get("mutualFundValue", 0.0)),
                            "lic": float(profile_data.get("lic", 0.0)),
                            "ulip": float(profile_data.get("ulip", 0.0)),
                            "fd5yr": float(profile_data.get("fd5yr", 0.0)),
                            "nsc": float(profile_data.get("nsc", 0.0)),
                            "sukanya": float(profile_data.get("sukanyaSamriddhi", 0.0))
                        },
                        "loans": {
                            "home_loan": float(profile_data.get("homeLoanPrincipal", 0.0)),
                            "home_loan_interest": float(profile_data.get("homeLoanInterest", 0.0)),
                            "ev_loan_interest": float(profile_data.get("evLoanInterest", 0.0)),
                            "education_loan": float(profile_data.get("eduLoanInterest", 0.0))
                        },
                        "insurance": {
                            "health_insurance": float(profile_data.get("healthInsuranceSelf", 0.0)) > 0 or float(profile_data.get("healthInsuranceParents", 0.0)) > 0,
                            "health_insurance_self": float(profile_data.get("healthInsuranceSelf", 0.0)),
                            "health_insurance_parents": float(profile_data.get("healthInsuranceParents", 0.0)),
                            "life_insurance": float(profile_data.get("lic", 0.0))
                        },
                        "real_estate": {
                            "properties": 1 if profile_data.get("hasProperty") else 0,
                            "rental_income": float(profile_data.get("rentalIncome", 0.0))
                        },
                        "financial_year": "2025-26"
                    },
                    "profile_data": profile_data,
                    "last_updated": profile_rec.updated_at.isoformat() if (profile_rec and profile_rec.updated_at) else datetime.now(timezone.utc).isoformat()
                }
            }

        except Exception as e:
            self.logger.error(f"Error fetching user profile: {e}")
            return None

    async def get_user_income_history(
        self,
        user_id: str,
        years: int = 3
    ) -> dict[str, Any] | None:
        """
        Get the user's stated income for the current year from their saved
        financial profile.

        This used to return a hardcoded placeholder (literal salary_income:
        500000) for every user regardless of their actual profile — every
        downstream tax figure computed from it was therefore fake, not just
        the slab math applied to it. There is no historical-year storage yet
        (`years` beyond the current one), so only one real entry is returned;
        a user with no saved profile gets an empty history rather than an
        invented number.
        """
        try:
            from sqlalchemy import select

            from backend.core.rules import fy_for_date
            from backend.db.orm_models import FinancialProfile

            stmt = select(FinancialProfile).where(FinancialProfile.user_id == user_id)
            res = await self.db.execute(stmt)
            profile_rec = res.scalar_one_or_none()

            if not profile_rec or not profile_rec.profile_data:
                return {"user_id": user_id, "income_history": []}

            profile_data = profile_rec.profile_data
            profession = profile_data.get("profession", "")
            salary = float(profile_data.get("salaryCtc", 0.0)) if profession == "salaried" else 0.0
            business = float(profile_data.get("businessIncome", 0.0)) + float(profile_data.get("freelanceIncome", 0.0))
            rental = float(profile_data.get("rentalIncome", 0.0))
            other = float(profile_data.get("otherIncome", 0.0)) + float(profile_data.get("dividendIncome", 0.0))
            total = (
                salary + business + rental + other
                + float(profile_data.get("capitalGainsStcg", 0.0))
                + float(profile_data.get("capitalGainsLtcg", 0.0))
            )

            return {
                "user_id": user_id,
                "income_history": [
                    {
                        "financial_year": fy_for_date(datetime.now(timezone.utc).date()),
                        "salary_income": salary,
                        "business_income": business,
                        "rental_income": rental,
                        "other_income": other,
                        "total_income": total,
                        "tax_paid": float(profile_data.get("tds_paid", 0.0)),
                    }
                ],
            }
        except Exception as e:
            self.logger.error(f"Error fetching income history: {e}")
            return None

    async def get_user_deductions(self, user_id: str) -> dict[str, Any] | None:
        """Get user's claimed deductions, capped to real statutory limits.

        Previously returned raw uncapped sums under section labels ("NPS",
        "Sec24b") that don't match the section codes `backend.core`'s
        ruleset actually recognises, with a wrong 80D limit (75,000 — that's
        80C's limit, copy-pasted) and NPS employee+employer lumped into one
        claim despite being different sections (80CCD(1B) vs 80CCD(2)) with
        different caps. Every cap below matches the ones already applied in
        `useProfileStore.calculateTax` on the frontend, so a user sees the
        same capped figure in both places rather than two different guesses.
        """
        try:
            from sqlalchemy import select

            from backend.db.orm_models import FinancialProfile

            stmt = select(FinancialProfile).where(FinancialProfile.user_id == user_id)
            res = await self.db.execute(stmt)
            profile_rec = res.scalar_one_or_none()

            profile_data = profile_rec.profile_data if (profile_rec and profile_rec.profile_data) else {}

            raw_80c = (
                float(profile_data.get("ppf", 0)) + float(profile_data.get("elss", 0))
                + float(profile_data.get("lic", 0)) + float(profile_data.get("ulip", 0))
                + float(profile_data.get("fd5yr", 0)) + float(profile_data.get("nsc", 0))
                + float(profile_data.get("sukanyaSamriddhi", 0)) + float(profile_data.get("homeLoanPrincipal", 0))
            )
            c_80c = min(150000.0, raw_80c)

            self_premium = float(profile_data.get("healthInsuranceSelf", 0))
            parents_premium = float(profile_data.get("healthInsuranceParents", 0))
            parents_limit = 50000.0 if (profile_data.get("seniorParents") or profile_data.get("superSeniorParents")) else 25000.0
            c_80d = min(25000.0, self_premium) + min(parents_limit, parents_premium)

            nps_employee = float(profile_data.get("npsEmployee", 0))
            c_80ccd_1b = min(50000.0, nps_employee)

            nps_employer = float(profile_data.get("npsEmployer", 0))
            salary_ctc = float(profile_data.get("salaryCtc", 0))
            # 80CCD(2): employer NPS contribution, capped as a % of salary
            # rather than a flat rupee limit. 10% is the private-sector rate;
            # government employees get 14%, which this does not distinguish —
            # a conservative (lower) figure rather than an unclaimable one.
            c_80ccd_2 = min(salary_ctc * 0.10, nps_employer) if salary_ctc > 0 else 0.0

            home_loan_interest = float(profile_data.get("homeLoanInterest", 0))
            c_24b = min(200000.0, home_loan_interest)

            edu_loan_interest = float(profile_data.get("eduLoanInterest", 0))

            ev_loan_interest = float(profile_data.get("evLoanInterest", 0))
            c_80eeb = min(150000.0, ev_loan_interest)

            savings_interest = float(profile_data.get("savingsBankInterest", 0))
            c_80tta = min(10000.0, savings_interest)

            donations = float(profile_data.get("donationsU80G", 0))
            hra = float(profile_data.get("hra", 0))
            lta = float(profile_data.get("lta", 0))

            total_deductions = (
                c_80c + c_80d + c_80ccd_1b + c_80ccd_2 + c_24b
                + edu_loan_interest + c_80eeb + c_80tta + donations + hra + lta
            )

            # Flat — no {"success", "result"} envelope. `get_user_income_history`
            # and `get_user_investments` return flat like this too, but a
            # previous version of this method wrapped its own return in one,
            # and `tools/registry.py`'s dispatcher ALSO wraps every tool
            # result in {"success", "result"} — stacking a second one meant
            # every caller's `.get("result", {}).get("deductions", ...)` was
            # reading a level too shallow and silently got `{}`/`[]` back.
            # Confirmed live in advanced_calculator.py, but tax_strategy.py
            # and compliance_checker.py have the same single-unwrap pattern
            # and were affected identically.
            return {
                "user_id": user_id,
                "deductions": {
                    "80C": {
                        "claimed": c_80c,
                        "limit": 150000,
                        "items": [
                            {"type": "PPF", "amount": float(profile_data.get("ppf", 0))},
                            {"type": "ELSS", "amount": float(profile_data.get("elss", 0))},
                            {"type": "LIC Premium", "amount": float(profile_data.get("lic", 0))},
                            {"type": "ULIP", "amount": float(profile_data.get("ulip", 0))},
                            {"type": "5-Year FD", "amount": float(profile_data.get("fd5yr", 0))},
                            {"type": "NSC", "amount": float(profile_data.get("nsc", 0))},
                            {"type": "Sukanya Samriddhi", "amount": float(profile_data.get("sukanyaSamriddhi", 0))},
                            {"type": "Home Loan Principal", "amount": float(profile_data.get("homeLoanPrincipal", 0))}
                        ]
                    },
                    "80D": {
                        "claimed": c_80d,
                        "limit": 25000 + parents_limit,
                        "items": [
                            {"type": "Health Insurance (Self)", "amount": self_premium},
                            {"type": "Health Insurance (Parents)", "amount": parents_premium}
                        ]
                    },
                    "80CCD_1B": {
                        "claimed": c_80ccd_1b,
                        "limit": 50000,
                        "items": [
                            {"type": "NPS Employee Contribution (additional)", "amount": nps_employee}
                        ]
                    },
                    "80CCD_2": {
                        "claimed": c_80ccd_2,
                        "limit": "10% of salary (private sector)",
                        "items": [
                            {"type": "NPS Employer Contribution", "amount": nps_employer}
                        ]
                    },
                    "24b": {
                        "claimed": c_24b,
                        "limit": 200000,
                        "items": [
                            {"type": "Home Loan Interest", "amount": home_loan_interest}
                        ]
                    },
                    "80E": {
                        "claimed": edu_loan_interest,
                        "limit": None,
                        "items": [
                            {"type": "Education Loan Interest", "amount": edu_loan_interest}
                        ]
                    },
                    "80EEB": {
                        "claimed": c_80eeb,
                        "limit": 150000,
                        "items": [
                            {"type": "EV Loan Interest", "amount": ev_loan_interest}
                        ]
                    },
                    "80TTA": {
                        "claimed": c_80tta,
                        "limit": 10000,
                        "items": [
                            {"type": "Savings Account Interest", "amount": savings_interest}
                        ]
                    },
                    "80G": {
                        "claimed": donations,
                        "limit": None,
                        "items": [
                            {"type": "Donations", "amount": donations}
                        ]
                    },
                    "10_13A": {
                        "claimed": hra,
                        "limit": None,
                        "items": [
                            {"type": "HRA Exemption (as declared)", "amount": hra}
                        ]
                    },
                    "LTA": {
                        "claimed": lta,
                        "limit": None,
                        "items": [
                            {"type": "Leave Travel Allowance", "amount": lta}
                        ]
                    }
                },
                "total_deductions": total_deductions
            }
        except Exception as e:
            self.logger.error(f"Error fetching deductions: {e}")
            return None

    async def get_user_investments(self, user_id: str) -> dict[str, Any]:
        """Get user's investment portfolio."""
        try:
            return {
                "user_id": user_id,
                "investments": {
                    "equity": {
                        "direct_stocks": 300000,
                        "mutual_funds": 200000,
                        "total": 500000
                    },
                    "debt": {
                        "ppf": 150000,
                        "fixed_deposits": 200000,
                        "bonds": 100000,
                        "total": 450000
                    },
                    "real_estate": {
                        "primary_property": 5000000,
                        "rental_property": 0,
                        "total": 5000000
                    },
                    "others": {
                        "gold": 50000,
                        "cryptocurrency": 10000,
                        "total": 60000
                    }
                },
                "total_portfolio_value": 6010000
            }
        except Exception as e:
            self.logger.error(f"Error fetching investments: {e}")
            return None


# ============================================================================
# ANALYSIS STORAGE TOOL
# ============================================================================

class AnalysisStorageTool:
    """Store and retrieve agent analysis results."""

    def __init__(self, db_session):
        """Initialize with database session."""
        self.db = db_session
        self.logger = logging.getLogger("tool.storage")

    async def save_analysis(
        self,
        user_id: str,
        analysis_type: AnalysisType,
        analysis_data: dict[str, Any],
        agent_name: str = "unknown",
        conversation_id: str | None = None
    ) -> dict[str, Any]:
        """
        Save analysis results.
        
        Args:
            user_id: User ID
            analysis_type: Type of analysis
            analysis_data: Analysis results
            agent_name: Which agent performed analysis
            conversation_id: Associated conversation
            
        Returns:
            Saved analysis record
        """
        try:
            # TODO: Save to database
            analysis_record = {
                "analysis_id": f"analysis_{user_id}_{int(datetime.now(timezone.utc).timestamp() * 1000)}",
                "user_id": user_id,
                "type": analysis_type.value,
                "agent": agent_name,
                "data": analysis_data,
                "conversation_id": conversation_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": "saved"
            }

            self.logger.info(f"Saved {analysis_type.value} analysis for user {user_id}")

            return analysis_record

        except Exception as e:
            self.logger.error(f"Error saving analysis: {e}")
            return {"status": "error", "message": str(e)}

    async def save_recommendation(
        self,
        user_id: str,
        recommendation_type: str,
        recommendation: dict[str, Any],
        agent_name: str = "unknown"
    ) -> dict[str, Any]:
        """Save agent recommendation."""
        try:
            record = {
                "recommendation_id": f"rec_{user_id}_{int(datetime.now(timezone.utc).timestamp() * 1000)}",
                "user_id": user_id,
                "type": recommendation_type,
                "agent": agent_name,
                "recommendation": recommendation,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": "active"
            }

            self.logger.info(f"Saved {recommendation_type} recommendation for user {user_id}")

            return record

        except Exception as e:
            self.logger.error(f"Error saving recommendation: {e}")
            return {"status": "error", "message": str(e)}

    async def get_analysis_history(
        self,
        user_id: str,
        analysis_type: str | None = None,
        limit: int = 10
    ) -> list[dict[str, Any]]:
        """Get user's analysis history."""
        try:
            # TODO: Query from database
            return [
                {
                    "analysis_id": f"analysis_{user_id}_001",
                    "type": "tax_optimization",
                    "agent": "tax_optimizer_agent",
                    "created_at": "2024-06-01T10:00:00",
                    "summary": "Suggested 80C investment strategy"
                }
            ]
        except Exception as e:
            self.logger.error(f"Error fetching analysis history: {e}")
            return []

    async def get_recommendation_history(
        self,
        user_id: str,
        limit: int = 10
    ) -> list[dict[str, Any]]:
        """Get user's recommendations."""
        try:
            return []
        except Exception as e:
            self.logger.error(f"Error fetching recommendations: {e}")
            return []


# ============================================================================
# USER DATA UPDATE TOOL
# ============================================================================

class UserDataUpdateTool:
    """Update user's financial profile."""

    def __init__(self, db_session):
        """Initialize with database session."""
        self.db = db_session
        self.logger = logging.getLogger("tool.update")

    async def update_income(
        self,
        user_id: str,
        income_sources: dict[str, float]
    ) -> dict[str, Any]:
        """
        Update user's income information.
        
        Args:
            user_id: User ID
            income_sources: {salary: ..., business: ..., rental: ..., etc}
            
        Returns:
            Updated profile
        """
        try:
            # TODO: Update in database
            return {
                "user_id": user_id,
                "updated": True,
                "income_sources": income_sources,
                "total_income": sum(income_sources.values()),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            self.logger.error(f"Error updating income: {e}")
            return {"error": str(e)}

    async def update_deductions(
        self,
        user_id: str,
        deductions: dict[str, float]
    ) -> dict[str, Any]:
        """Update user's deductions."""
        try:
            # TODO: Update in database
            return {
                "user_id": user_id,
                "updated": True,
                "deductions": deductions,
                "total_deductions": sum(deductions.values()),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            self.logger.error(f"Error updating deductions: {e}")
            return {"error": str(e)}

    async def update_investments(
        self,
        user_id: str,
        investments: dict[str, Any]
    ) -> dict[str, Any]:
        """Update user's investments."""
        try:
            # TODO: Update in database
            return {
                "user_id": user_id,
                "updated": True,
                "investments": investments,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            self.logger.error(f"Error updating investments: {e}")
            return {"error": str(e)}


# ============================================================================
# AUDIT LOG TOOL
# ============================================================================

class AuditLogTool:
    """Log all agent actions and decisions."""

    def __init__(self, db_session):
        """Initialize with database session."""
        self.db = db_session
        self.logger = logging.getLogger("tool.audit")

    async def log_agent_action(
        self,
        user_id: str,
        agent_name: str,
        action: str,
        input_data: dict[str, Any],
        output_data: dict[str, Any],
        conversation_id: str | None = None
    ) -> dict[str, Any]:
        """Log an agent action for audit trail."""
        try:
            log_entry = {
                "log_id": f"log_{user_id}_{int(datetime.now(timezone.utc).timestamp() * 1000)}",
                "user_id": user_id,
                "agent": agent_name,
                "action": action,
                "input": input_data,
                "output": output_data,
                "conversation_id": conversation_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            # TODO: Save to database
            self.logger.info(f"Logged action: {agent_name}/{action} for user {user_id}")

            return {"status": "logged", "log_id": log_entry["log_id"]}

        except Exception as e:
            self.logger.error(f"Error logging action: {e}")
            return {"status": "error", "message": str(e)}

    async def get_user_audit_log(
        self,
        user_id: str,
        limit: int = 50
    ) -> list[dict[str, Any]]:
        """Get audit log for user."""
        try:
            # TODO: Query from database
            return []
        except Exception as e:
            self.logger.error(f"Error fetching audit log: {e}")
            return []


# ============================================================================
# TOOL FACTORY
# ============================================================================

class DatabaseToolFactory:
    """Factory to create database tools with session."""

    def __init__(self, db_session):
        """Initialize with database session."""
        self.db_session = db_session

    def create_tools(self) -> dict[str, Any]:
        """Create all database tools."""
        return {
            "user_data": UserFinancialDataTool(self.db_session),
            "storage": AnalysisStorageTool(self.db_session),
            "update": UserDataUpdateTool(self.db_session),
            "audit": AuditLogTool(self.db_session)
        }
