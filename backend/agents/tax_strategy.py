"""
Tax Strategy Agent
==================

Handles long-term tax planning, regime transition modeling, and tax harvesting strategies.
"""

import time
import logging
from typing import Dict, Any, List
from datetime import datetime

from backend.agents.base_agent import TaxAgent, AgentOutput, confidence_score, derive_confidence

logger = logging.getLogger(__name__)


class TaxStrategyAgent(TaxAgent):
    """
    Design long-term tax strategy and regime transitions:
    
    • 3-Year Projection comparing Old vs New tax regimes
    • Tax-loss and tax-gain harvesting guidance
    • Strategy suggestions for salary restructuring & investments
    """
    
    def __init__(self):
        super().__init__("tax_strategy_agent", "tax_strategy")
        
    async def execute(
        self,
        user_query: str,
        user_context: Dict[str, Any],
        tools=None,
        **kwargs
    ) -> AgentOutput:
        """
        Formulate a long-term tax optimization strategy.
        """
        start_time = time.time()
        if tools is not None:
            self.set_tools(tools)
            
        try:
            self.logger.info(f"Starting long-term tax strategy analysis for: {user_query}")
            
            # Fetch user details
            user_profile = {}
            user_deductions_list = []
            if self.tools:
                profile_res = await self.call_tool(
                    "get_user_profile",
                    user_id=user_context.get("user_id", "unknown")
                )
                if profile_res.get("success"):
                    user_profile = profile_res.get("result", {})
                    
                deductions_res = await self.call_tool(
                    "get_user_deductions",
                    user_id=user_context.get("user_id", "unknown")
                )
                if deductions_res.get("success"):
                    user_deductions_list = deductions_res.get("result", {}).get("deductions", [])
            
            annual_income = float(user_profile.get("financial_profile", {}).get("annual_income", 0)) or float(user_context.get("annual_income", 0)) or 1200000.0
            
            # Deductions calculations for Old Regime (80C, 80D, etc.)
            total_deductions = 0.0
            for d in user_deductions_list:
                total_deductions += float(d.get("amount", 0))
            if total_deductions == 0:
                # Fallback to standard assumptions if database has no records
                total_deductions = float(user_context.get("current_deductions") or 150000.0) # default 80C
                
            # Add standard deduction (₹50,000 for old, ₹75,000 for new in FY 24-25)
            old_deductions_total = total_deductions + 50000.0
            new_deductions_total = 75000.0
            
            # 1. 3-Year Projection Model
            #
            # The financial year is resolved explicitly: backend.core has no
            # default year, which is what stops a projection silently using
            # last year's slabs.
            from backend.tools.calculation import current_fy
            fy = user_context.get("fy") or current_fy()

            projections = []
            growth_rate = 0.10 # 10% annual income growth
            
            current_income = annual_income
            for year in range(1, 4):
                # Calculate Old regime tax
                old_taxable = max(0.0, current_income - old_deductions_total)
                old_tax = self._regime_tax(old_taxable, "old", fy)
                
                # Calculate New regime tax
                new_taxable = max(0.0, current_income - new_deductions_total)
                new_tax = self._regime_tax(new_taxable, "new", fy)
                
                better_regime = "New Regime" if new_tax < old_tax else "Old Regime"
                savings = abs(old_tax - new_tax)
                
                projections.append({
                    "year": f"Year {year}",
                    "projected_income": current_income,
                    "old_regime_tax": old_tax,
                    "new_regime_tax": new_tax,
                    "recommended_regime": better_regime,
                    "annual_savings": savings
                })
                
                current_income *= (1.0 + growth_rate)
                
            # 2. Recommendations & Strategies
            recommendations = []
            
            y1_rec = projections[0]
            recommendations.append(
                f"For the current financial year, the {y1_rec['recommended_regime']} is more beneficial for you, "
                f"saving you ₹{y1_rec['annual_savings']:,.2f} in taxes."
            )
            
            # Check regime switch trigger point
            different_regimes = set(p["recommended_regime"] for p in projections)
            if len(different_regimes) > 1:
                recommendations.append(
                    "Switching Trigger Warning: As your income grows, your optimal tax regime will change. "
                    "Plan to switch to the New Regime as your income crosses higher slabs where standard deductions yield diminishing utility."
                )
            else:
                recommendations.append(
                    f"Consistently, the {list(different_regimes)[0]} remains the optimal choice for the next 3 years based on your deduction structure."
                )
                
            # Add tax harvesting tip
            recommendations.append(
                "Tax-Loss/Gain Harvesting: Capitalize on the ₹1.25 Lakhs tax-free limit for Long-Term Capital Gains (LTCG) on equity. "
                "Consider selling and immediately repurchasing shares with accumulated gains to reset your acquisition costs tax-free before March 31."
            )
            
            result = {
                "base_annual_income": annual_income,
                "assumed_annual_growth_rate": f"{growth_rate*100:.0f}%",
                "old_regime_deductions_applied": old_deductions_total,
                "three_year_projections": projections,
                "recommendations": recommendations
            }
            
            execution_time = (time.time() - start_time) * 1000
            
            return self._create_output(
                result=result,
                status="success",
                confidence=confidence_score(derive_confidence()),
                reasoning="Completed 3-year income/tax regime projections and formulated transition strategies.",
                execution_time_ms=execution_time
            )
            
        except Exception as e:
            self.logger.error(f"Error in TaxStrategyAgent: {e}", exc_info=True)
            execution_time = (time.time() - start_time) * 1000
            return self._create_output(
                result={"error": str(e)},
                status="error",
                confidence=0.0,  # execution failed — not a score
                reasoning=f"Failure generating tax strategy projections: {str(e)}",
                execution_time_ms=execution_time
            )

    # ── DEM-006 ──────────────────────────────────────────────────────────
    # `_calculate_old_regime_tax` and `_calculate_new_regime_tax` deleted.
    # They were a second, divergent tax engine: FY 2024-25 slabs, no surcharge,
    # no marginal relief, and a hard rebate cliff at Rs 7,00,001 where one extra
    # rupee of income added about Rs 26,000 of tax. Both regimes now come from
    # one engine and one rule pack, so the comparison is internally consistent.

    @staticmethod
    def _regime_tax(taxable_income: float, regime: str, fy: str, age: int = 0) -> float:
        from backend.tools.calculation import TaxCalculationEngine
        result = TaxCalculationEngine.calculate_income_tax(
            taxable_income, fy=fy, regime=regime, age=age
        )
        return float(result["total_tax"])
