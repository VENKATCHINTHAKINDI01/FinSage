"""
Step 8.2: Eligibility Verifier Agent
====================================

Verify user eligibility for specific schemes.
Check requirements, docs, deadlines.
"""

import time
import logging
from typing import Dict, Any, List
from datetime import datetime

from backend.agents.base_agent import TaxAgent, AgentOutput

logger = logging.getLogger(__name__)


class EligibilityVerifierAgent(TaxAgent):
    """
    Verify eligibility for specific schemes.
    
    • Check requirement conditions
    • Verify documentation
    • Check deadlines
    • Provide guidance
    """
    
    def __init__(self):
        super().__init__("eligibility_verifier_agent", "eligibility_check")
    
    async def execute(
        self,
        user_query: str,
        user_context: Dict[str, Any],
        tools=None,
        **kwargs
    ) -> AgentOutput:
        """
        Verify scheme eligibility.
        
        Workflow:
          1. Extract scheme from query
          2. Check eligibility criteria
          3. Identify missing docs
          4. Check deadlines
          5. Provide guidance
        """
        start_time = time.time()
        
        if tools is not None:
            self.set_tools(tools)
        
        try:
            self.logger.info(f"Starting eligibility verification for user {user_context.get('user_id')}")
            
            # STEP 1: Extract scheme code from query
            scheme_code = self._extract_scheme_code(user_query)
            
            if not scheme_code:
                execution_time = (time.time() - start_time) * 1000
                return self._create_output(
                    result={"message": "No specific scheme mentioned. Which scheme would you like to verify?"},
                    status="info",
                    confidence=0.5,
                    reasoning="No scheme code extracted from the query",
                    execution_time_ms=execution_time
                )
            
            # Fetch user financial profile if tools are available
            user_profile = {}
            if self.tools:
                profile_res = await self.call_tool(
                    "get_user_profile",
                    user_id=user_context.get("user_id", "unknown")
                )
                if profile_res.get("success"):
                    user_profile = profile_res.get("result", {})
            
            # Extract basic info
            basic_info = user_profile.get("basic_info", {})
            financial_profile = user_profile.get("financial_profile", {})
            
            # Resolve age, annual_income, health_insurance, and education_loan
            age = basic_info.get("age") or user_context.get("age") or 35
            annual_income = financial_profile.get("annual_income") or user_context.get("annual_income") or 0.0
            
            insurance_info = financial_profile.get("insurance", {})
            has_health_insurance = (
                insurance_info.get("health_insurance", False) 
                or user_context.get("health_insurance") 
                or False
            )
            
            loans_info = financial_profile.get("loans", {})
            education_loan_amount = loans_info.get("education_loan", 0)
            has_education_loan = (
                education_loan_amount > 0 
                or user_context.get("education_loan") 
                or False
            )
            
            # STEP 2: Check eligibility
            if self.tools:
                eligibility = await self.call_tool(
                    "check_scheme_eligibility",
                    scheme_code=scheme_code,
                    user_age=age,
                    user_income=annual_income,
                    has_health_insurance=has_health_insurance,
                    has_education_loan=has_education_loan
                )
                
                eligible = eligibility.get("result", {}).get("eligible", False)
                reasons = eligibility.get("result", {}).get("reasons", [])
            else:
                eligible = False
                reasons = ["Unable to verify - tools not initialized"]
            
            # STEP 3: Get scheme details
            if self.tools:
                details = await self.call_tool(
                    "get_scheme_details",
                    scheme_code=scheme_code
                )
                scheme_info = details.get("result", {}).get("details", {})
            else:
                scheme_info = {}
            
            # STEP 4: Prepare verification result
            if eligible:
                result = self._create_eligible_response(scheme_code, scheme_info)
            else:
                result = self._create_ineligible_response(scheme_code, reasons)
            
            execution_time = (time.time() - start_time) * 1000
            
            return self._create_output(
                result=result,
                status="success",
                confidence=0.90 if eligible else 0.85,
                reasoning=f"Eligibility verification completed for scheme {scheme_code}.",
                execution_time_ms=execution_time
            )
        
        except Exception as e:
            self.logger.error(f"Error in eligibility verifier: {e}", exc_info=True)
            execution_time = (time.time() - start_time) * 1000
            
            return self._create_output(
                result={"error": str(e)},
                status="error",
                confidence=0.0,
                reasoning=f"Error: {str(e)}",
                execution_time_ms=execution_time
            )
    
    def _extract_scheme_code(self, query: str) -> str:
        """Extract scheme code from query."""
        # Common scheme codes
        codes = ["80C", "80D", "80E", "80TTA", "80TTB", "80CCD", "80DDB", "80G", "80U"]
        
        query_upper = query.upper()
        
        for code in codes:
            if code in query_upper:
                return code
        
        return None
    
    def _create_eligible_response(self, scheme_code: str, scheme_info: Dict) -> Dict[str, Any]:
        """Create response for eligible user."""
        return {
            "eligible": True,
            "scheme_code": scheme_code,
            "scheme_name": scheme_info.get("name", "Unknown"),
            "status": "✅ YOU ARE ELIGIBLE",
            "limit": scheme_info.get("limit"),
            "benefits": scheme_info.get("benefits", []),
            "documents_required": scheme_info.get("documents_needed", []),
            "next_steps": [
                "1. Gather all required documents",
                "2. Visit official government website",
                "3. Fill application form",
                "4. Submit with documents",
                "5. Track your application"
            ],
            "tips": [
                "Apply early - avoid last-minute rush",
                "Keep digital copies of all documents",
                "Note your application reference number"
            ]
        }
    
    def _create_ineligible_response(self, scheme_code: str, reasons: List[str]) -> Dict[str, Any]:
        """Create response for ineligible user."""
        alternatives = self._get_alternatives(scheme_code)
        
        return {
            "eligible": False,
            "scheme_code": scheme_code,
            "status": "❌ NOT ELIGIBLE",
            "reasons": reasons,
            "why_not_eligible": reasons,
            "alternative_schemes": alternatives,
            "what_to_do": [
                f"Option 1: Wait until {self._get_eligibility_date(scheme_code)}",
                "Option 2: Consider alternative schemes above",
                "Option 3: Consult a tax professional"
            ]
        }
    
    def _get_alternatives(self, current_scheme: str) -> List[str]:
        """Get alternative schemes."""
        alternatives = {
            "80C": ["80D", "80CCD"],
            "80D": ["80C", "80DDB"],
            "80E": ["80C", "80CCD"],
            "80TTA": ["80TTB", "80C"],
            "80TTB": ["80C", "80D"],
            "80CCD": ["80C", "80D"]
        }
        
        return alternatives.get(current_scheme, ["Consult a tax professional"])
    
    def _get_eligibility_date(self, scheme_code: str) -> str:
        """Get when user might become eligible."""
        # Simplified - in real system, calculate based on requirements
        return "after next financial year"
