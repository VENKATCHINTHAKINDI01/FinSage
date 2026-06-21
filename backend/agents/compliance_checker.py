"""
Step 9.1: Compliance Checker Agent
==================================

India-specific compliance assessment with database persistence.
"""

import time
import logging
from typing import Dict, Any, List
from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from backend.agents.base_agent import TaxAgent, AgentOutput
from backend.db.orm_models import ComplianceReport, RedFlagLog
from backend.services.india_tax_data_fetcher import india_tax_data

logger = logging.getLogger(__name__)


class ComplianceCheckerAgent(TaxAgent):
    """
    Check tax compliance status.
    
    • Audit readiness assessment
    • Document verification
    • Red flag detection (India-specific)
    • Compliance scoring (0-100)
    • Save to database
    """
    
    def __init__(self, db: Session = None):
        super().__init__("compliance_checker_agent", "compliance_check")
        self.db = db
    
    def set_db(self, db: Session):
        """Set database session."""
        self.db = db
        return self
    
    async def execute(
        self,
        user_query: str,
        user_context: Dict[str, Any],
        tools=None,
        **kwargs
    ) -> AgentOutput:
        """
        Check compliance status.
        
        Workflow:
          1. Get user data from DB
          2. Check India-specific documentation
          3. Detect red flags
          4. Calculate compliance score
          5. Generate recommendations
          6. Save to database
        """
        start_time = time.time()
        
        if tools is not None:
            self.set_tools(tools)
            
        try:
            user_id = user_context.get("user_id")
            self.logger.info(f"Checking compliance for user {user_id}")
            
            # STEP 1: Get user data
            user_data = {}
            user_deductions = []
            
            if self.tools:
                user_profile = await self.call_tool(
                    "get_user_profile",
                    user_id=user_id or "unknown"
                )
                if user_profile.get("success"):
                    user_data = user_profile.get("result", {})
                
                deductions_res = await self.call_tool(
                    "get_user_deductions",
                    user_id=user_id or "unknown"
                )
                if deductions_res.get("success"):
                    res_val = deductions_res.get("result", {})
                    if isinstance(res_val, dict):
                        user_deductions = res_val.get("deductions", [])
                    elif isinstance(res_val, list):
                        user_deductions = res_val
            else:
                user_data = user_context
            
            # STEP 2: Check India-specific documentation
            doc_status = self._check_india_documentation(user_data, user_context, user_deductions)
            
            # STEP 3: Detect India-specific red flags
            red_flags = await self._detect_india_red_flags(user_data, user_context, user_deductions)
            
            # STEP 4: Calculate compliance score
            compliance_score = self._calculate_compliance_score(
                doc_status,
                red_flags,
                user_context
            )
            
            # STEP 5: Assess audit readiness
            audit_ready = compliance_score >= 80
            
            # STEP 6: Generate recommendations
            recommendations = self._generate_india_recommendations(
                doc_status,
                red_flags,
                compliance_score
            )
            
            result = {
                "compliance_score": compliance_score,
                "audit_ready": audit_ready,
                "audit_readiness_status": "✅ Audit Ready" if audit_ready else "⚠️ Needs Work",
                "document_status": doc_status,
                "red_flags": red_flags,
                "red_flag_count": len(red_flags),
                "missing_documents": doc_status.get("missing", []),
                "recommendations": recommendations,
                "next_steps": self._get_next_steps(compliance_score),
                "risk_level": self._assess_risk(compliance_score),
                "itr_deadline": "July 31, 2025",
                "days_to_deadline": self._days_to_deadline()
            }
            
            # STEP 7: Save to database
            db_session = self.db
            if not db_session:
                try:
                    from backend.orchestrator.graph import db_session_var
                    db_session = db_session_var.get()
                except Exception:
                    db_session = None
            
            if db_session and user_id:
                await self._save_to_database(user_id, result, db_session)
            
            execution_time = (time.time() - start_time) * 1000
            
            return self._create_output(
                result=result,
                status="success",
                confidence=0.88,
                reasoning="Compliance score, red flags, and document completeness calculated dynamically.",
                execution_time_ms=execution_time
            )
        
        except Exception as e:
            self.logger.error(f"Error checking compliance: {e}", exc_info=True)
            execution_time = (time.time() - start_time) * 1000
            
            return self._create_output(
                result={"error": str(e)},
                status="error",
                confidence=0.0,
                reasoning=f"Error checking compliance: {str(e)}",
                execution_time_ms=execution_time
            )
    
    def _check_india_documentation(
        self,
        user_data: Dict[str, Any],
        user_context: Dict[str, Any],
        user_deductions: List[Any]
    ) -> Dict[str, Any]:
        """
        Check India-specific required documents.
        
        Based on:
        • Income Tax Department requirements
        • Form 16/Form 16A
        • 26AS (TDS statement)
        • Schedule CG (if capital gains)
        """
        required_docs = {
            "identity": ["PAN Card", "Aadhaar Card"],
            "address": ["Address Proof", "Utility Bill/Rental Agreement"],
            "income": ["Form 16 (Salary)", "26AS (TDS Statement)", "Bank Statements"],
            "deductions": [
                "Investment Receipts (80C)",
                "Insurance Certificates (80D)",
                "Medical Bills (80DDB)",
                "Education Documents (80E)"
            ],
            "capital_gains": ["Schedule CG", "Gain/Loss Statement"],
            "business": ["Profit & Loss Account", "Balance Sheet", "Audit Report"],
            "gst": ["GSTR-1", "GSTR-2", "GSTR-9"]
        }
        
        present = []
        missing = []
        
        financial_profile = user_data.get("financial_profile", {})
        annual_income = financial_profile.get("annual_income") or user_context.get("annual_income") or 0
        employment_type = financial_profile.get("employment_type") or user_context.get("employment_type", "salaried")
        has_capital_gains = user_context.get("has_capital_gains") or financial_profile.get("has_capital_gains") or False
        gst_registered = user_context.get("gst_registered") or financial_profile.get("gst_registered") or False
        
        # Identity and address are assumed present for simple user profile tracking
        present.extend(required_docs["identity"])
        present.extend(required_docs["address"])
        
        # Income check
        if annual_income > 0:
            present.extend(required_docs["income"])
        else:
            missing.extend(required_docs["income"])
        
        # Deductions check
        has_deductions = False
        if user_deductions:
            has_deductions = len(user_deductions) > 0
        elif isinstance(financial_profile.get("investments"), dict):
            has_deductions = len(financial_profile["investments"]) > 0
        elif user_context.get("deductions"):
            has_deductions = len(user_context["deductions"]) > 0
            
        if has_deductions:
            present.extend(required_docs["deductions"])
        
        # Capital Gains
        if has_capital_gains:
            present.extend(required_docs["capital_gains"])
        
        # Business Docs
        if employment_type in ["business", "self-employed"]:
            present.extend(required_docs["business"])
            
        # GST
        if gst_registered:
            present.extend(required_docs["gst"])
        
        # Documents not found
        all_required = []
        for docs in required_docs.values():
            all_required.extend(docs)
        
        total_tracked = len(present) + len(missing)
        completeness = (len(present) / total_tracked * 100) if total_tracked > 0 else 100
        
        return {
            "present": present,
            "missing": missing,
            "completeness": completeness,
            "status": "✅ Complete" if completeness >= 80 else "⚠️ Incomplete"
        }
    
    async def _detect_india_red_flags(
        self,
        user_data: Dict[str, Any],
        user_context: Dict[str, Any],
        user_deductions: List[Any]
    ) -> List[Dict[str, Any]]:
        """
        Detect India-specific red flags from IT Department patterns.
        """
        flags = []
        
        # Get red flag patterns from tax data
        tax_data = await india_tax_data.get_current_tax_data()
        red_flag_patterns = tax_data["red_flags"]
        
        financial_profile = user_data.get("financial_profile", {})
        annual_income = financial_profile.get("annual_income") or user_context.get("annual_income") or 0
        
        # Calculate total deductions
        total_deductions = sum(float(d.get("amount", 0)) for d in user_deductions if isinstance(d, dict))
        if total_deductions == 0 and isinstance(financial_profile.get("investments"), dict):
            total_deductions = sum(float(v) for v in financial_profile["investments"].values() if isinstance(v, (int, float)))
        elif total_deductions == 0 and isinstance(user_context.get("deductions"), dict):
            total_deductions = sum(float(d.get("amount", 0)) for d in user_context["deductions"].values() if isinstance(d, dict))
        
        # Flag 1: High income with low deductions (India-specific)
        if annual_income > 2000000 and (total_deductions / annual_income) < 0.05:
            flags.append({
                "flag": "⚠️ High income with low deductions (₹20L+)",
                "severity": "Medium",
                "action": "Maximize valid deductions under 80C, 80D, 80E"
            })
        
        # Flag 2: TDS mismatch (India-specific)
        tds_paid = user_context.get("tds_paid", 0) or financial_profile.get("tds_paid", 0)
        calculated_tax = user_context.get("calculated_tax", 0) or annual_income * 0.20
        
        if tds_paid > 0 and abs(tds_paid - calculated_tax) > calculated_tax * 0.15:
            flags.append({
                "flag": "🔴 TDS paid vs 26AS mismatch",
                "severity": "High",
                "action": "Verify Form 16 data matches 26AS statement"
            })
        
        # Flag 3: GST compliance (India-specific)
        turnover = user_context.get("turnover", 0) or financial_profile.get("turnover", 0)
        gst_threshold = tax_data["gst"]["registration_threshold"]
        
        if turnover > gst_threshold and not (user_context.get("gst_registered") or financial_profile.get("gst_registered")):
            flags.append({
                "flag": "🔴 GST registration required but not done",
                "severity": "High",
                "action": f"Register for GST (Turnover ₹{gst_threshold:,.0f}+)"
            })
        
        # Flag 4: Advance tax default (India-specific)
        if annual_income > 1000000 and not (user_context.get("advance_tax_paid") or financial_profile.get("advance_tax_paid")):
            flags.append({
                "flag": "⚠️ Advance tax may not have been paid",
                "severity": "High",
                "action": "Verify Q1-Q4 advance tax payments made"
            })
        
        # Flag 5: Form 16 vs actual income mismatch
        form_16_income = user_context.get("form_16_income", 0) or financial_profile.get("form_16_income", 0)
        if form_16_income > 0 and abs(annual_income - form_16_income) > annual_income * 0.10:
            flags.append({
                "flag": "⚠️ Income in ITR vs Form 16 mismatch",
                "severity": "Medium",
                "action": "Ensure all income sources reported in ITR"
            })
        
        return flags[:5]  # Return top 5 flags
    
    def _calculate_compliance_score(
        self,
        doc_status: Dict[str, Any],
        red_flags: List[Dict],
        user_context: Dict[str, Any]
    ) -> int:
        """Calculate overall compliance score (0-100)."""
        score = 100
        
        # Deduct for missing docs
        doc_completeness = doc_status.get("completeness", 100)
        score -= (100 - doc_completeness) * 0.5
        
        # Deduct for red flags
        for flag in red_flags:
            severity = flag.get("severity", "Low")
            if severity == "High":
                score -= 20
            elif severity == "Medium":
                score -= 10
            else:
                score -= 5
        
        # Bonus for good practices
        if user_context.get("tds_paid", 0) > 0:
            score += 5
        if user_context.get("gst_registered"):
            score += 5
        if user_context.get("advance_tax_paid"):
            score += 5
        
        return max(0, min(100, int(score)))
    
    def _generate_india_recommendations(
        self,
        doc_status: Dict[str, Any],
        red_flags: List[Dict],
        compliance_score: int
    ) -> List[str]:
        """Generate India-specific recommendations."""
        recommendations = []
        
        if compliance_score < 60:
            recommendations.append("🔴 URGENT: Consult CA before ITR filing")
        elif compliance_score < 80:
            recommendations.append("🟡 Address below issues before ITR filing")
        else:
            recommendations.append("🟢 Ready to file ITR")
        
        # Document recommendations
        missing = doc_status.get("missing", [])
        if missing:
            recommendations.append(f"Gather missing documents: {', '.join(missing[:3])}")
        
        # Red flag actions
        for flag in red_flags:
            recommendations.append(f"{flag['flag']} → {flag['action']}")
        
        return recommendations
    
    def _get_next_steps(self, score: int) -> List[str]:
        """Get next steps based on compliance score."""
        if score >= 80:
            return [
                "1. Review ITR form selection (ITR-1/2/4/5)",
                "2. Verify all income sources in ITR",
                "3. File ITR before July 31, 2025",
                "4. Verify within 30 days"
            ]
        elif score >= 60:
            return [
                "1. Resolve red flags (see above)",
                "2. Collect missing documents",
                "3. Verify with CA if needed",
                "4. Then file ITR"
            ]
        else:
            return [
                "1. SCHEDULE CA CONSULTATION",
                "2. Get professional audit done",
                "3. Resolve all compliance issues",
                "4. File ITR with CA assistance"
            ]
    
    def _assess_risk(self, score: int) -> str:
        """Assess audit risk level."""
        if score >= 85:
            return "🟢 Low Risk - Audit unlikely"
        elif score >= 70:
            return "🟡 Medium Risk - Possible scrutiny"
        else:
            return "🔴 High Risk - Audit likely"
    
    def _days_to_deadline(self) -> int:
        """Days remaining to ITR filing deadline."""
        from datetime import date
        deadline = date(2025, 7, 31)
        today = date.today()
        days = (deadline - today).days
        return max(0, days)
    
    async def _save_to_database(self, user_id: str, result: Dict[str, Any], db_session):
        """Save compliance report to database."""
        try:
            compliance_report = ComplianceReport(
                user_id=user_id,
                compliance_score=result["compliance_score"],
                audit_readiness=result["audit_ready"],
                red_flags=result["red_flags"],
                missing_documents=result.get("missing_documents"),
                recommendations=result["recommendations"],
                risk_level=result["risk_level"],
                saved_status="saved"
            )
            
            db_session.add(compliance_report)
            
            # Also save individual red flags
            for flag in result.get("red_flags", []):
                red_flag_log = RedFlagLog(
                    user_id=user_id,
                    flag_name=flag.get("flag", ""),
                    severity=flag.get("severity", "Low"),
                    description=flag.get("flag", ""),
                    action_required=flag.get("action", ""),
                    resolved=False
                )
                db_session.add(red_flag_log)
            
            # Handle AsyncSession commit vs standard Session commit
            if isinstance(db_session, AsyncSession):
                await db_session.commit()
            else:
                db_session.commit()
                
            self.logger.info(f"Compliance report saved for user {user_id}")
        
        except Exception as e:
            self.logger.error(f"Error saving to database: {e}")
            if isinstance(db_session, AsyncSession):
                await db_session.rollback()
            else:
                db_session.rollback()
