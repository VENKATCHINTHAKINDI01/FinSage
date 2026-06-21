"""
Cross-Border Tax Agent
======================

Handles foreign income, DTAA, residential status, and foreign assets disclosures.
"""

import time
import logging
from typing import Dict, Any, List
from datetime import datetime

from backend.agents.base_agent import TaxAgent, AgentOutput

logger = logging.getLogger(__name__)


class CrossBorderTaxAgent(TaxAgent):
    """
    Evaluate cross-border tax liabilities and NRI rules for India:
    
    • Residential Status Check (Section 6(1))
    • DTAA Relief & Foreign Tax Credit (FTC) under Section 90/91
    • Schedule FA (Foreign Assets) disclosures under Black Money Act
    """
    
    def __init__(self):
        super().__init__("cross_border_tax_agent", "cross_border_tax")
        
    async def execute(
        self,
        user_query: str,
        user_context: Dict[str, Any],
        tools=None,
        **kwargs
    ) -> AgentOutput:
        """
        Analyze residency and foreign income tax aspects.
        """
        start_time = time.time()
        if tools is not None:
            self.set_tools(tools)
            
        try:
            self.logger.info(f"Starting cross-border tax analysis for query: {user_query}")
            
            # 1. Fetch user profile if available
            user_profile = {}
            if self.tools:
                profile_res = await self.call_tool(
                    "get_user_profile",
                    user_id=user_context.get("user_id", "unknown")
                )
                if profile_res.get("success"):
                    user_profile = profile_res.get("result", {})
                    
            # 2. Extract inputs from user context / query / profile
            basic_info = user_profile.get("basic_info", {})
            financial_profile = user_profile.get("financial_profile", {})
            
            # Days in India during current FY
            days_current_fy = user_context.get("days_in_india") or basic_info.get("days_in_india") or 182
            # Days in India during preceding 4 FYs
            days_preceding_4_years = user_context.get("days_preceding_4_years") or basic_info.get("days_preceding_4_years") or 365
            # Citizen or Person of Indian Origin (PIO) visit criteria
            is_citizen_or_pio = user_context.get("is_citizen_or_pio", True)
            
            # Foreign income parameters
            foreign_income = user_context.get("foreign_income") or financial_profile.get("foreign_income") or 0.0
            foreign_tax_paid = user_context.get("foreign_tax_paid") or financial_profile.get("foreign_tax_paid") or 0.0
            foreign_country = user_context.get("foreign_country") or financial_profile.get("foreign_country") or "USA"
            has_foreign_assets = user_context.get("has_foreign_assets") or financial_profile.get("has_foreign_assets") or False
            
            # 3. Determine Residential Status under Section 6(1)
            # Resident if:
            # - In India for 182 days or more
            # OR
            # - In India for 60 days or more (120 days or more for Citizens/PIOs with Indian income > 15L) AND 365 days or more in preceding 4 years
            residency = "Resident"
            residency_reason = ""
            
            if days_current_fy >= 182:
                residency = "Resident"
                residency_reason = "Stay in India is 182 days or more in the current financial year."
            elif days_current_fy >= 60 and days_preceding_4_years >= 365:
                # If citizen/PIO visiting India, 60 days is replaced by 182 days (or 120 days if Indian-sourced income > 15L)
                indian_sourced_income = float(financial_profile.get("annual_income", 0))
                if is_citizen_or_pio:
                    threshold = 120 if indian_sourced_income > 1500000 else 182
                    if days_current_fy >= threshold:
                        residency = "Resident"
                        residency_reason = f"Stay in India is >= {threshold} days for a visiting citizen/PIO with Indian income, and >= 365 days in the preceding 4 years."
                    else:
                        residency = "Non-Resident Indian (NRI)"
                        residency_reason = f"Stay in India is less than {threshold} days for a visiting citizen/PIO."
                else:
                    residency = "Resident"
                    residency_reason = "Stay in India is 60 days or more in the current year, and 365 days or more in the preceding 4 years."
            else:
                residency = "Non-Resident Indian (NRI)"
                residency_reason = "Does not satisfy stay criteria for Residency (stay < 182 days, or stay < 60 days, or preceding years stay < 365 days)."
                
            # If Resident, determine if Ordinarily Resident (ROR) or Not Ordinarily Resident (RNOR)
            resident_subtype = ""
            if residency == "Resident":
                # Typically RNOR if non-resident in 9 out of 10 preceding years, OR stay in preceding 7 years <= 729 days.
                nri_prev_10_years = user_context.get("nri_prev_10_years", 9)
                stay_prev_7_years = user_context.get("stay_prev_7_years", 729)
                
                if nri_prev_10_years >= 9 or stay_prev_7_years <= 729:
                    resident_subtype = "Resident but Not Ordinarily Resident (RNOR)"
                else:
                    resident_subtype = "Resident and Ordinarily Resident (ROR)"
                    
            status_display = resident_subtype if residency == "Resident" else residency
            
            # 4. Formulate DTAA Relief & foreign tax credit recommendations
            dtaa_relief_eligible = False
            dtaa_relief_amount = 0.0
            recommendations = []
            
            if foreign_income > 0:
                dtaa_relief_eligible = True
                # Unilateral or bilateral relief check
                if foreign_tax_paid > 0:
                    # Relief is lower of (foreign tax paid) or (Indian tax rate on that income)
                    indian_tax_rate = 0.30 # assumed marginal bracket
                    estimated_indian_tax = foreign_income * indian_tax_rate
                    dtaa_relief_amount = min(foreign_tax_paid, estimated_indian_tax)
                    
                    recommendations.append(
                        f"You are eligible for Foreign Tax Credit (FTC) of ₹{dtaa_relief_amount:,.2f} under Section 90/91 "
                        f"to avoid double taxation on your income from {foreign_country}."
                    )
                    recommendations.append(
                        "You must file Form 67 on or before the due date of filing your ITR to claim this credit."
                    )
                else:
                    recommendations.append(
                        f"You have foreign income from {foreign_country} but did not report foreign tax paid. "
                        f"Check if tax was withheld at source (TDS) and obtain a tax certificate."
                    )
            
            # 5. Schedule FA (Foreign Assets) rules
            schedule_fa_required = False
            if residency == "Resident" and resident_subtype == "Resident and Ordinarily Resident (ROR)":
                if has_foreign_assets or foreign_income > 0:
                    schedule_fa_required = True
                    recommendations.append(
                        "As a Resident and Ordinarily Resident (ROR) with foreign assets/income, you MUST file Schedule FA "
                        "in your ITR to disclose foreign bank accounts, RSUs, ESOPs, or mutual funds."
                    )
                    recommendations.append(
                        "⚠️ WARNING: Non-disclosure of foreign assets in Schedule FA attracts a flat penalty of ₹10 Lakhs "
                        "under the Black Money (Undisclosed Foreign Income and Assets) Act."
                    )
            elif residency == "Non-Resident Indian (NRI)" or resident_subtype == "Resident but Not Ordinarily Resident (RNOR)":
                recommendations.append(
                    f"As an {status_display}, your global / foreign income is not taxable in India, and "
                    f"you are not required to file Schedule FA for foreign assets."
                )
                
            if not recommendations:
                recommendations.append("Your residency status does not indicate complex foreign assets or tax implications at this time.")
                
            result = {
                "residential_status": status_display,
                "residency_criteria_reason": residency_reason,
                "foreign_income_reported": foreign_income,
                "foreign_tax_paid": foreign_tax_paid,
                "dtaa_relief_eligible": dtaa_relief_eligible,
                "estimated_ftc_relief": dtaa_relief_amount,
                "schedule_fa_required": schedule_fa_required,
                "recommendations": recommendations
            }
            
            execution_time = (time.time() - start_time) * 1000
            
            return self._create_output(
                result=result,
                status="success",
                confidence=0.90,
                reasoning=f"Computed residency as {status_display} and verified DTAA/Schedule FA applicability.",
                execution_time_ms=execution_time
            )
            
        except Exception as e:
            self.logger.error(f"Error in CrossBorderTaxAgent: {e}", exc_info=True)
            execution_time = (time.time() - start_time) * 1000
            return self._create_output(
                result={"error": str(e)},
                status="error",
                confidence=0.0,
                reasoning=f"Failure evaluating cross border tax: {str(e)}",
                execution_time_ms=execution_time
            )
