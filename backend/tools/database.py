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
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Get user's income history for multiple years.
        
        Args:
            user_id: User ID
            years: Number of years to retrieve
            
        Returns:
            {
                "financial_years": [
                    {"fy": "2024-25", "income": {...}},
                    {"fy": "2023-24", "income": {...}}
                ]
            }
        """
        try:
            # Placeholder
            return {
                "user_id": user_id,
                "income_history": [
                    {
                        "financial_year": "2024-25",
                        "salary_income": 500000,
                        "business_income": 0,
                        "rental_income": 0,
                        "other_income": 0,
                        "total_income": 500000,
                        "tax_paid": 50000
                    },
                    {
                        "financial_year": "2023-24",
                        "salary_income": 450000,
                        "business_income": 0,
                        "rental_income": 0,
                        "other_income": 0,
                        "total_income": 450000,
                        "tax_paid": 40000
                    }
                ]
            }
        except Exception as e:
            self.logger.error(f"Error fetching income history: {e}")
            return None

    async def get_user_deductions(self, user_id: str) -> dict[str, Any]:
        """Get user's claimed deductions."""
        try:
            from sqlalchemy import select

            from backend.db.orm_models import FinancialProfile

            stmt = select(FinancialProfile).where(FinancialProfile.user_id == user_id)
            res = await self.db.execute(stmt)
            profile_rec = res.scalar_one_or_none()

            profile_data = profile_rec.profile_data if (profile_rec and profile_rec.profile_data) else {}

            c_80c = float(profile_data.get("ppf", 0)) + float(profile_data.get("elss", 0)) + float(profile_data.get("lic", 0)) + float(profile_data.get("ulip", 0)) + float(profile_data.get("fd5yr", 0)) + float(profile_data.get("nsc", 0)) + float(profile_data.get("sukanyaSamriddhi", 0)) + float(profile_data.get("homeLoanPrincipal", 0))
            c_80d = float(profile_data.get("healthInsuranceSelf", 0)) + float(profile_data.get("healthInsuranceParents", 0))
            c_nps = float(profile_data.get("npsEmployee", 0)) + float(profile_data.get("npsEmployer", 0))

            return {
                "success": True,
                "result": {
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
                            "limit": 75000,
                            "items": [
                                {"type": "Health Insurance (Self)", "amount": float(profile_data.get("healthInsuranceSelf", 0))},
                                {"type": "Health Insurance (Parents)", "amount": float(profile_data.get("healthInsuranceParents", 0))}
                            ]
                        },
                        "NPS": {
                            "claimed": c_nps,
                            "limit": 200000,
                            "items": [
                                {"type": "NPS Employee Contribution", "amount": float(profile_data.get("npsEmployee", 0))},
                                {"type": "NPS Employer Contribution", "amount": float(profile_data.get("npsEmployer", 0))}
                            ]
                        },
                        "Sec24b": {
                            "claimed": float(profile_data.get("homeLoanInterest", 0)),
                            "limit": 200000,
                            "items": [
                                {"type": "Home Loan Interest", "amount": float(profile_data.get("homeLoanInterest", 0))}
                            ]
                        },
                        "80E": {
                            "claimed": float(profile_data.get("eduLoanInterest", 0)),
                            "limit": None,
                            "items": [
                                {"type": "Education Loan Interest", "amount": float(profile_data.get("eduLoanInterest", 0))}
                            ]
                        },
                        "80EEB": {
                            "claimed": float(profile_data.get("evLoanInterest", 0)),
                            "limit": 150000,
                            "items": [
                                {"type": "EV Loan Interest", "amount": float(profile_data.get("evLoanInterest", 0))}
                            ]
                        }
                    },
                    "total_deductions": c_80c + c_80d + c_nps + float(profile_data.get("homeLoanInterest", 0)) + float(profile_data.get("eduLoanInterest", 0)) + float(profile_data.get("evLoanInterest", 0))
                }
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
