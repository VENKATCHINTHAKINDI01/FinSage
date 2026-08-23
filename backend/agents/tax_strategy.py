"""
Tax Strategy Agent
==================

Handles long-term tax planning, regime transition modeling, and tax harvesting strategies.
"""

import logging
import time
from typing import Any

from backend.agents.base_agent import AgentOutput, TaxAgent, confidence_score, derive_confidence

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
        user_context: dict[str, Any],
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

            # 1. 3-Year Projection Model — AGT-001.
            #
            # What was here: the standard deduction hardcoded as ₹50,000 (old)
            # and ₹75,000 (new), under a comment reading "FY 24-25". Those
            # happen to still be the FY 2026-27 figures, which is worse than
            # being wrong — the agent was right by coincidence and would have
            # gone stale silently the first time a Finance Act moved either
            # number, with nothing in the codebase to notice. The rule packs
            # exist precisely so that a figure like this is READ, not restated.
            #
            # It was also re-implementing the regime comparison: subtract
            # deductions by hand, call the engine twice, compare. That is a
            # second comparison to keep in step with the first, and the tool
            # layer already has `compare_regimes`, which additionally returns
            # the exact deduction total at which the answer flips — the thing
            # a user planning three years ahead actually needs.
            #
            # The financial year is resolved explicitly: backend.core has no
            # default year, which is what stops a projection silently using
            # last year's slabs.
            from backend.tools.calculation import TaxCalculationEngine, current_fy
            fy = user_context.get("fy") or current_fy()

            projections = []
            growth_rate = 0.10 # 10% annual income growth

            current_income = annual_income
            for year in range(1, 4):
                comparison = TaxCalculationEngine.compare_regimes(
                    gross_income=current_income,
                    deductions={"total": total_deductions},
                    fy=fy,
                    age=int(user_context.get("age", 0) or 0),
                    is_salary=True,
                )
                old_tax = float(comparison["old"]["total_tax"])
                new_tax = float(comparison["new"]["total_tax"])

                projections.append({
                    "year": f"Year {year}",
                    "projected_income": current_income,
                    "old_regime_tax": old_tax,
                    "new_regime_tax": new_tax,
                    "recommended_regime": (
                        "New Regime" if comparison["better_regime"] == "new"
                        else "Old Regime"
                    ),
                    "annual_savings": float(comparison["saving"]),
                    # The engine's own explanation, so the projection carries
                    # the reasoning rather than only the answer.
                    "summary": comparison.get("summary"),
                    "breakeven_deductions": comparison.get("breakeven_deductions"),
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
                # The user's OWN deductions. The standard deduction is no
                # longer added in here — each regime's is applied by the engine
                # from the rule pack, and reporting a combined figure invited
                # exactly the hardcoding this change removed.
                "old_regime_deductions_applied": total_deductions,
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
                reasoning=f"Failure generating tax strategy projections: {e!s}",
                execution_time_ms=execution_time
            )

    # ── DEM-006 ──────────────────────────────────────────────────────────
    # `_calculate_old_regime_tax` and `_calculate_new_regime_tax` deleted.
    # They were a second, divergent tax engine: FY 2024-25 slabs, no surcharge,
    # no marginal relief, and a hard rebate cliff at Rs 7,00,001 where one extra
    # rupee of income added about Rs 26,000 of tax. Both regimes now come from
    # one engine and one rule pack, so the comparison is internally consistent.

    # AGT-001 (2026-08-23): `_regime_tax` deleted along with its callers. The
    # projection now uses `TaxCalculationEngine.compare_regimes`, which applies
    # each regime's standard deduction from the rule pack instead of having
    # this agent subtract a hardcoded one first. Deleted rather than kept
    # "in case": an unused helper that computes tax is exactly the thing
    # someone reaches for next time, and it takes a TAXABLE income, so calling
    # it with a gross one silently skips the standard deduction.
