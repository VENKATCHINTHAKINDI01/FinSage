"""
Wealth Planner Agent
===================

Integrates long-term wealth generation and retirement planning with Indian tax laws.
"""

import time
import logging
from typing import Dict, Any, List
from datetime import datetime

from backend.agents.base_agent import TaxAgent, AgentOutput

logger = logging.getLogger(__name__)


class WealthPlannerAgent(TaxAgent):
    """
    Formulate long-term wealth and tax-integrated retirement plans:
    
    • NPS Retirement withdrawal tax analysis (60% tax-free / 40% taxable annuity)
    • PPF EEE extension modeling
    • Capital gains rollover exemptions (Section 54 and 54EC)
    """
    
    def __init__(self):
        super().__init__("wealth_planner_agent", "wealth_planning")
        
    async def execute(
        self,
        user_query: str,
        user_context: Dict[str, Any],
        tools=None,
        **kwargs
    ) -> AgentOutput:
        """
        Analyze wealth planning and retirement tax dynamics.
        """
        start_time = time.time()
        if tools is not None:
            self.set_tools(tools)
            
        try:
            self.logger.info(f"Starting wealth planner tax analysis for: {user_query}")
            
            # Fetch user profile and investments
            user_profile = {}
            user_investments = {}
            if self.tools:
                profile_res = await self.call_tool(
                    "get_user_profile",
                    user_id=user_context.get("user_id", "unknown")
                )
                if profile_res.get("success"):
                    user_profile = profile_res.get("result", {})
                    
                investments_res = await self.call_tool(
                    "get_user_investments",
                    user_id=user_context.get("user_id", "unknown")
                )
                if investments_res.get("success"):
                    user_investments = investments_res.get("result", {}).get("investments", {})
                    
            basic_info = user_profile.get("basic_info", {})
            age = basic_info.get("age") or user_context.get("age") or 35
            
            # Extract inputs
            nps_balance = float(user_investments.get("nps", 0)) or float(user_context.get("nps_balance", 0)) or 1000000.0
            ppf_balance = float(user_investments.get("ppf", 0)) or float(user_context.get("ppf_balance", 0)) or 500000.0
            capital_gain_to_reinvest = float(user_context.get("capital_gain", 0))
            
            recommendations = []
            result = {}
            
            # 1. NPS Retirement Modeling
            # Upon reaching 60, up to 60% can be withdrawn tax-free as lump sum.
            # Minimum 40% must be used for purchasing annuity (which pays monthly pension taxable at slab rates).
            lump_sum_tax_free = nps_balance * 0.60
            compulsory_annuity = nps_balance * 0.40
            
            recommendations.append(
                f"NPS Plan (Current Balance: ₹{nps_balance:,.2f}): At age 60, you can withdraw a maximum lump sum of "
                f"₹{lump_sum_tax_free:,.2f} (60%) completely tax-free. The remaining ₹{compulsory_annuity:,.2f} (40%) "
                f"must be reinvested in an annuity, and the resulting monthly pension will be taxed at your slab rates."
            )
            recommendations.append(
                "Maximizing NPS Deductions: You can contribute an additional ₹50,000 per year specifically under Section 80CCD(1B), "
                "which is over and above the Section 80C limit of ₹1.5 Lakhs."
            )
            
            # 2. PPF extension modeling
            recommendations.append(
                f"PPF Plan (Current Balance: ₹{ppf_balance:,.2f}): PPF holds Exempt-Exempt-Exempt (EEE) status. "
                "After the initial 15-year maturity, you can extend the account indefinitely in blocks of 5 years, "
                "with or without fresh contributions, maintaining the tax-free status on all interest earned."
            )
            
            # 3. Capital Gains Rollover (Sections 54 & 54EC)
            if capital_gain_to_reinvest > 0:
                result["reinvestable_gains"] = capital_gain_to_reinvest
                
                # Section 54EC bonds are issued by NHAI/REC/PFC, interest is taxable, maturity is tax-free. Capped at ₹50 Lakhs.
                sec_54ec_limit = 5000000.0
                eligible_54ec = min(capital_gain_to_reinvest, sec_54ec_limit)
                
                recommendations.append(
                    f"Capital Gains Deferral: For your capital gains of ₹{capital_gain_to_reinvest:,.2f}, you can invest up to "
                    f"₹{eligible_54ec:,.2f} in Section 54EC Bonds (NHAI/REC) within 6 months of the asset transfer date "
                    f"to claim an exemption from Long-Term Capital Gains tax."
                )
                if capital_gain_to_reinvest > sec_54ec_limit:
                    excess = capital_gain_to_reinvest - sec_54ec_limit
                    recommendations.append(
                        f"Note: Section 54EC investments are capped at ₹50 Lakhs. The remaining ₹{excess:,.2f} will be "
                        f"subject to LTCG tax unless reinvested in residential property under Section 54/54F."
                    )
            
            result = {
                "age": age,
                "nps_balance": nps_balance,
                "nps_tax_free_lump_sum_60_percent": lump_sum_tax_free,
                "nps_compulsory_annuity_40_percent": compulsory_annuity,
                "ppf_balance": ppf_balance,
                "recommendations": recommendations
            }
            
            execution_time = (time.time() - start_time) * 1000
            
            return self._create_output(
                result=result,
                status="success",
                confidence=0.90,
                reasoning="Calculated retirement tax implications for NPS and PPF and provided reinvestment exemption advice.",
                execution_time_ms=execution_time
            )
            
        except Exception as e:
            self.logger.error(f"Error in WealthPlannerAgent: {e}", exc_info=True)
            execution_time = (time.time() - start_time) * 1000
            return self._create_output(
                result={"error": str(e)},
                status="error",
                confidence=0.0,
                reasoning=f"Failure generating wealth planner tax analysis: {str(e)}",
                execution_time_ms=execution_time
            )
