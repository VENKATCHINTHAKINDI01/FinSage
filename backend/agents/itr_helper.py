"""
Step 9.2: ITR Helper Agent
==========================

Complete ITR filing guidance for India (ITR-1, 2, 4, 5).
Database persistence + India-specific rules.
"""

import time
import logging
from typing import Dict, Any, List
from datetime import datetime, date

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from backend.agents.base_agent import TaxAgent, AgentOutput
from backend.db.orm_models import ITRFiling
from backend.services.india_tax_data_fetcher import india_tax_data

logger = logging.getLogger(__name__)


class ITRHelperAgent(TaxAgent):
    """
    Guide users through ITR filing.
    
    • Form selection (ITR-1, 2, 4, 5)
    • Step-by-step filing guide
    • India-specific documentation
    • Deadline tracking
    • TDS/Advance tax validation
    • Save to database
    """
    
    def __init__(self, db: Session = None):
        super().__init__("itr_helper_agent", "tax_filing")
        self.db = db
    
    def set_tools(self, tools):
        """Inject tools."""
        self.tools = tools
        return self
    
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
        Provide India-specific ITR filing guidance.
        
        Workflow:
          1. Determine applicable ITR form
          2. Get India tax filing requirements
          3. Provide step-by-step guide
          4. List common mistakes
          5. Validate TDS & advance tax
          6. Save to database
        """
        start_time = time.time()
        
        if tools is not None:
            self.set_tools(tools)
            
        try:
            user_id = user_context.get("user_id")
            self.logger.info(f"Providing ITR guidance for user {user_id}")
            
            # STEP 1: Get user data from database tools if available
            user_data = {}
            if self.tools:
                user_profile = await self.call_tool(
                    "get_user_profile",
                    user_id=user_id or "unknown"
                )
                if user_profile.get("success"):
                    user_data = user_profile.get("result", {})
                    
            # Resolve profile details
            basic_info = user_data.get("basic_info", {})
            financial_profile = user_data.get("financial_profile", {})
            
            # Merge context
            merged_context = {
                "annual_income": financial_profile.get("annual_income") or user_context.get("annual_income") or 0,
                "employment_type": basic_info.get("employment_type") or user_context.get("employment_type") or "salaried",
                "has_capital_gains": user_context.get("has_capital_gains") or financial_profile.get("has_capital_gains") or False
            }
            
            # Get India tax data
            tax_data = await india_tax_data.get_current_tax_data()
            itr_forms = tax_data["itr_forms"]
            
            # Determine applicable ITR form
            applicable_form = await india_tax_data.validate_itr_form(merged_context)
            form_details = itr_forms.get(applicable_form, {})
            
            # STEP 2: Get India-specific filing requirements
            requirements = self._get_india_filing_requirements(
                applicable_form,
                merged_context,
                tax_data
            )
            
            # STEP 3: Get step-by-step filing guide
            filing_steps = self._get_itr_filing_steps(applicable_form)
            
            # STEP 4: Get common mistakes (India-specific)
            common_mistakes = tax_data.get("common_itr_mistakes", [])
            
            # STEP 5: Validate TDS & Advance Tax
            tds_validation = self._validate_tds_compliance(merged_context)
            advance_tax_validation = self._validate_advance_tax(merged_context, tax_data)
            
            # STEP 6: Get important dates
            important_dates = tax_data["important_dates"]
            
            result = {
                "recommended_form": applicable_form,
                "form_details": {
                    "name": form_details.get("name"),
                    "applicable": form_details.get("applicable"),
                    "complexity": self._get_complexity(applicable_form),
                    "income_types": [x.capitalize() for x in form_details.get("income_types", [])]
                },
                "financial_year": tax_data["financial_year"],
                "assessment_year": tax_data["assessment_year"],
                
                "filing_requirements": requirements,
                "step_by_step_guide": filing_steps,
                "estimated_time": f"{len(filing_steps) * 15} minutes",
                
                "common_mistakes": common_mistakes,
                "what_to_avoid": [
                    f"❌ {mistake}" for mistake in common_mistakes[:5]
                ],
                
                "tds_validation": tds_validation,
                "advance_tax_validation": advance_tax_validation,
                
                "important_dates": {
                    "normal_deadline": important_dates["itr_normal_deadline"],
                    "extended_deadline": important_dates["itr_extended_deadline"],
                    "verification_deadline": important_dates["itr_verification"],
                    "q1_advance_tax": important_dates["q1_advance_tax"],
                    "q2_advance_tax": important_dates["q2_advance_tax"],
                    "q3_advance_tax": important_dates["q3_advance_tax"],
                    "q4_advance_tax": important_dates["q4_advance_tax"]
                },
                
                "filing_checklist": self._get_filing_checklist(applicable_form),
                "days_to_deadline": self._days_to_deadline(),
                
                "next_actions": [
                    "1. Gather all required documents (see above)",
                    "2. Download ITR form from incometax.gov.in",
                    "3. Create login on e-filing portal",
                    "4. Follow step-by-step guide above",
                    "5. Verify ITR within 30 days (critical!)"
                ],
                
                "documents_checklist": self._get_documents_by_form(applicable_form),
                "portal_url": "https://www.incometax.gov.in/home"
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
                await self._save_to_database(user_id, result, applicable_form, db_session)
            
            execution_time = (time.time() - start_time) * 1000
            
            return self._create_output(
                result=result,
                status="success",
                confidence=0.92,
                reasoning=f"Identified {applicable_form} as the applicable tax filing form.",
                execution_time_ms=execution_time
            )
        
        except Exception as e:
            self.logger.error(f"Error in ITR helper: {e}", exc_info=True)
            execution_time = (time.time() - start_time) * 1000
            
            return self._create_output(
                result={"error": str(e)},
                status="error",
                confidence=0.0,
                reasoning=f"Error providing ITR guidance: {str(e)}",
                execution_time_ms=execution_time
            )
    
    def _get_india_filing_requirements(
        self,
        itr_form: str,
        user_context: Dict[str, Any],
        tax_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Get India-specific ITR filing requirements."""
        
        base_requirements = {
            "documents": [
                "PAN Card",
                "Aadhaar Card (linked to PAN)",
                "Active Bank Account",
                "Income Proof (Form 16/26AS)"
            ],
            "digital_requirements": [
                "Email ID (active)",
                "Mobile number (registered)",
                "Bank account details",
                "Digital signature (if applicable)"
            ]
        }
        
        form_specific = {
            "ITR-1": {
                "documents": base_requirements["documents"] + [
                    "Form 16 (if salaried)",
                    "26AS statement",
                    "Bank interest statements",
                    "Rental income proof (if any)"
                ],
                "schedules": ["Schedule BA"],
                "gst_required": False
            },
            "ITR-2": {
                "documents": base_requirements["documents"] + [
                    "Capital gains statements",
                    "Foreign asset details",
                    "26AS statement"
                ],
                "schedules": ["Schedule CG", "Schedule FA"],
                "gst_required": False
            },
            "ITR-4": {
                "documents": base_requirements["documents"] + [
                    "Profit & Loss account",
                    "Balance sheet",
                    "GST registration (if applicable)",
                    "Audit report (if turnover > ₹1 crore)"
                ],
                "schedules": ["Schedule BP", "Schedule P&L"],
                "gst_required": True
            },
            "ITR-5": {
                "documents": base_requirements["documents"] + [
                    "All ITR-1/2/4 requirements",
                    "Foreign income details",
                    "Asset disclosure"
                ],
                "schedules": ["All schedules"],
                "gst_required": True
            }
        }
        
        requirements = form_specific.get(itr_form, {})
        
        return {
            "documents_needed": requirements.get("documents", []),
            "schedules_required": requirements.get("schedules", []),
            "gst_compliance": requirements.get("gst_required", False),
            "digital_copy_mandatory": True,
            "portal": "https://www.incometax.gov.in",
            "e_filing_available": True,
            "deadline": tax_data["important_dates"]["itr_normal_deadline"],
            "extended_deadline": tax_data["important_dates"]["itr_extended_deadline"],
            "verification_needed": "YES - Critical!"
        }
    
    def _get_itr_filing_steps(self, itr_form: str) -> List[Dict[str, Any]]:
        """Get step-by-step ITR filing guide for India."""
        
        base_steps = [
            {
                "step": 1,
                "action": "Visit https://www.incometax.gov.in",
                "details": "Go to e-filing portal, click 'File ITR'",
                "time_min": 2
            },
            {
                "step": 2,
                "action": "Login with PAN + Password",
                "details": "Use your registered email & password",
                "time_min": 2
            },
            {
                "step": 3,
                "action": "Select Assessment Year",
                "details": "Select 2025-26 for FY 2024-25",
                "time_min": 1
            },
            {
                "step": 4,
                "action": "Click 'File Return' > Select ITR Form",
                "details": f"Select {itr_form}",
                "time_min": 2
            },
            {
                "step": 5,
                "action": "Fill PERSONAL INFO SECTION",
                "details": "Name, address, contact, PAN, Aadhaar",
                "time_min": 5
            },
            {
                "step": 6,
                "action": "Fill INCOME DETAILS",
                "details": "Salary, business, rental, interest, capital gains",
                "time_min": 10
            },
            {
                "step": 7,
                "action": "Fill DEDUCTIONS SECTION",
                "details": "80C, 80D, 80E, 80TTA, 80CCD, etc.",
                "time_min": 10
            },
            {
                "step": 8,
                "action": "Enter TDS DETAILS",
                "details": "TDS from Form 16, 26AS, interest TDS",
                "time_min": 5
            },
            {
                "step": 9,
                "action": "Review SCHEDULE DATA",
                "details": "Schedule CG (capital gains), FA (foreign assets)",
                "time_min": 5
            },
            {
                "step": 10,
                "action": "VALIDATE & VERIFY",
                "details": "Check all data, resolve errors",
                "time_min": 5
            },
            {
                "step": 11,
                "action": "SUBMIT ITR",
                "details": "Click Submit, save acknowledgment",
                "time_min": 2
            },
            {
                "step": 12,
                "action": "VERIFY WITHIN 30 DAYS",
                "details": "Very Important! Verify via OTP/Aadhaar/DSC",
                "time_min": 5
            }
        ]
        
        return base_steps
    
    def _validate_tds_compliance(self, user_context: Dict[str, Any]) -> Dict[str, Any]:
        """Validate TDS compliance (India-specific)."""
        
        tds_paid = user_context.get("tds_paid", 0)
        calculated_tax = user_context.get("calculated_tax", 0)
        form_16_tds = user_context.get("form_16_tds", 0)
        
        variance = abs(tds_paid - form_16_tds) if form_16_tds > 0 else 0
        variance_percent = (variance / form_16_tds * 100) if form_16_tds > 0 else 0
        
        status = "✅ COMPLIANT" if variance_percent < 5 else "⚠️ MISMATCH - CHECK 26AS"
        
        return {
            "tds_paid": tds_paid,
            "form_16_shows": form_16_tds,
            "variance": variance,
            "variance_percent": variance_percent,
            "status": status,
            "action": "Verify 26AS statement on incometax.gov.in",
            "26as_url": "https://www.incometax.gov.in/26AS"
        }
    
    def _validate_advance_tax(
        self,
        user_context: Dict[str, Any],
        tax_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate advance tax payments (India-specific)."""
        
        annual_income = user_context.get("annual_income", 0)
        advance_tax_paid = user_context.get("advance_tax_paid", 0)
        
        # Advance tax required if estimated tax > ₹10,000
        estimated_tax = annual_income * 0.20
        advance_tax_required = estimated_tax > 10000
        
        status = "✅ DONE" if advance_tax_paid > 0 or not advance_tax_required else "⚠️ NOT PAID"
        
        return {
            "estimated_tax": estimated_tax,
            "advance_tax_required": advance_tax_required,
            "advance_tax_paid": advance_tax_paid,
            "status": status,
            "due_dates": [
                f"Q1 (Jun 15): ₹{estimated_tax * 0.25:,.0f}",
                f"Q2 (Sep 15): ₹{estimated_tax * 0.50:,.0f}",
                f"Q3 (Dec 15): ₹{estimated_tax * 0.75:,.0f}",
                f"Q4 (Mar 15): ₹{estimated_tax:,.0f}"
            ],
            "action": "Pay remaining advance tax if due dates passed"
        }
    
    def _get_complexity(self, itr_form: str) -> str:
        """Get complexity level of ITR form."""
        complexity_map = {
            "ITR-1": "Simple",
            "ITR-2": "Complex",
            "ITR-4": "Medium",
            "ITR-5": "Complex"
        }
        return complexity_map.get(itr_form, "Unknown")
    
    def _get_filing_checklist(self, itr_form: str) -> List[str]:
        """Get filing checklist (India-specific)."""
        return [
            "☐ Verified PAN is linked with Aadhaar",
            "☐ Gathered all required documents",
            "☐ Downloaded latest ITR form",
            "☐ Created e-filing account login",
            "☐ Verified 26AS statement",
            "☐ Verified Form 16 data",
            "☐ Calculated correct income",
            "☐ Listed all deductions with proof",
            "☐ Checked TDS credit",
            "☐ Calculated advance tax liability",
            "☐ Filled ITR form completely",
            "☐ Reviewed all schedules (CG, FA, etc)",
            "☐ Resolved all validation errors",
            "☐ Submitted ITR successfully",
            "☐ Got acknowledgment number",
            "☐ Saved acknowledgment PDF",
            "☐ Marked calendar to verify within 30 days",
            "☐ Verify ITR via OTP/DSC"
        ]
    
    def _get_documents_by_form(self, itr_form: str) -> List[str]:
        """Get complete documents list by form type."""
        
        docs = {
            "ITR-1": [
                "PAN Card & Aadhaar",
                "Form 16 (if salaried)",
                "26AS statement",
                "Bank interest certificates",
                "Rental income proofs",
                "Investment proofs (if claiming deductions)"
            ],
            "ITR-2": [
                "All ITR-1 documents",
                "Capital gains statements",
                "Schedule CG (capital gains detail)",
                "Foreign asset disclosures",
                "Schedule FA details"
            ],
            "ITR-4": [
                "PAN & Aadhaar",
                "Profit & Loss account",
                "Balance sheet",
                "GST registration & returns (if applicable)",
                "Audit report (if turnover > ₹1 crore)",
                "Bank statements (6 months)"
            ],
            "ITR-5": [
                "All ITR-1/2/4 documents",
                "Foreign income statements",
                "Foreign asset details",
                "Complete asset disclosure",
                "Business/Professional income docs"
            ]
        }
        
        return docs.get(itr_form, [])
    
    def _days_to_deadline(self) -> int:
        """Days remaining until ITR filing deadline."""
        deadline = date(2025, 7, 31)
        today = date.today()
        days = (deadline - today).days
        return max(0, days)
    
    async def _save_to_database(
        self,
        user_id: str,
        result: Dict[str, Any],
        itr_form: str,
        db_session
    ):
        """Save ITR filing details to database."""
        try:
            itr_filing = ITRFiling(
                user_id=user_id,
                financial_year=result["financial_year"],
                itr_form=itr_form,
                status="pending",
                form_details=result.get("form_details"),
                checklist=result.get("filing_checklist"),
                common_mistakes=result.get("common_mistakes"),
                important_dates=result.get("important_dates")
            )
            
            db_session.add(itr_filing)
            
            # Handle AsyncSession commit vs standard Session commit
            if isinstance(db_session, AsyncSession):
                await db_session.commit()
            else:
                db_session.commit()
                
            self.logger.info(f"ITR filing record saved for user {user_id}")
        
        except Exception as e:
            self.logger.error(f"Error saving to database: {e}")
            if isinstance(db_session, AsyncSession):
                await db_session.rollback()
            else:
                db_session.rollback()
