"""
Tax deduction agent - identifies deductible expenses and calculates savings.
"""

import logging
import time
from typing import Any

from backend.agents.base_agent import AgentOutput, TaxAgent, confidence_score, derive_confidence
from backend.llm import get_llm

logger = logging.getLogger(__name__)



class TaxDeductionAgent(TaxAgent):
    """
    Identifies tax-deductible expenses based on user's situation.
    
    Example:
        agent = TaxDeductionAgent()
        result = await agent.execute(
            "I spent $5000 on equipment for my business this year",
            {"employment_type": "business", "annual_income": 100000}
        )
    """

    def __init__(self):
        super().__init__("tax_deduction_agent")

    async def execute(
        self,
        user_query: str,
        user_context: dict[str, Any],
        **kwargs
    ) -> AgentOutput:
        """
        Analyze user query and identify deductible expenses.
        
        Returns:
            AgentOutput with deduction recommendations
        """
        start_time = time.time()

        try:
            # Preprocess query
            processed_query = await self.preprocess(user_query)

            # Get deductions using LLM
            deductions = await self._identify_deductions(
                processed_query,
                user_context
            )

            # Tax saving, by recomputing — AGT-001.
            #
            # This was `total_deduction * tax_bracket`, against a slab table
            # written into `_estimate_tax_bracket` whose first threshold was
            # ₹2,50,000 — the OLD regime's basic exemption, applied to
            # everybody, when the new regime's is ₹4,00,000 and the new regime
            # is the default.
            #
            # But the deeper problem is the multiplication itself, and the tool
            # layer already says so in `calculate_deduction_benefit`'s own
            # docstring: "Never amount × marginal_rate: that estimate is wrong
            # wherever the deduction crosses a rebate or surcharge boundary,
            # which is exactly where it matters most." The documented example
            # is a ₹2.1L employer-NPS contribution worth ₹81,900 that a
            # marginal-rate estimate values at ₹63,000. The tool computes the
            # tax twice and subtracts, which is right by construction.
            annual_income = float(user_context.get("annual_income", 0) or 0)
            total_deduction = sum(d.get("amount", 0) for d in deductions)

            from backend.tools.calculation import TaxCalculationEngine

            benefit = TaxCalculationEngine.calculate_deduction_benefit(
                deduction_amount=total_deduction,
                current_taxable_income=annual_income,
                fy=user_context.get("fy") or None,
                regime=user_context.get("regime", "old"),
                age=int(user_context.get("age", 0) or 0),
            )

            # Postprocess result
            result = {
                "deductions": deductions,
                "total_deduction_amount": total_deduction,
                # The rate this deduction ACTUALLY achieved, derived from the
                # two computations, rather than the bracket it was assumed to
                # sit in. Where a deduction crosses the s.87A rebate the two
                # differ by a lot, and the true figure is the interesting one.
                "effective_benefit_rate": benefit["effective_benefit_rate"],
                "estimated_tax_savings": float(benefit["tax_savings"]),
                "tax_before": float(benefit["tax_before"]),
                "tax_after": float(benefit["tax_after"]),
                "recommendations": await self._get_recommendations(deductions)
            }

            result = await self.postprocess(result)

            execution_time = (time.time() - start_time) * 1000  # Convert to ms

            logger.info(f"Tax deduction analysis completed: ${total_deduction} deductions identified")

            return self._create_output(
                result=result,
                status="success",
                confidence=confidence_score(derive_confidence()),
                reasoning="Identified deductible expenses based on user's situation",
                execution_time_ms=execution_time
            )

        except Exception as e:
            logger.error(f"Error in tax deduction agent: {e}")
            execution_time = (time.time() - start_time) * 1000

            return self._create_output(
                result={"error": str(e)},
                status="error",
                confidence=0.0,  # execution failed — not a score
                reasoning=f"Error during analysis: {e!s}",
                execution_time_ms=execution_time
            )

    async def _identify_deductions(
        self,
        user_query: str,
        user_context: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Use LLM to identify deductible expenses from user query."""

        employment_type = user_context.get("employment_type", "individual")

        prompt = f"""Based on the user's situation, identify tax-deductible expenses.

User's situation:
- Employment type: {employment_type}
- Annual income: ${user_context.get('annual_income', 0):,.0f}

User's statement: "{user_query}"

Identify all potential tax deductions. For each, provide:
1. Category (e.g., "business equipment", "home office", "professional fees")
2. Estimated amount
3. Deductibility (high/medium/low confidence)
4. Notes for tax filing

Respond in JSON format:
{{
  "deductions": [
    {{
      "category": "Business Equipment",
      "amount": 5000,
      "deductibility": "high",
      "notes": "Purchase of computer for business use in {year}"
    }}
  ]
}}

Important: Respond ONLY with valid JSON."""

        try:
            message = await get_llm().complete(prompt, max_tokens=1000)

            response_text = message.text.strip()
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            import json
            response_data = json.loads(response_text)

            return response_data.get("deductions", [])

        except Exception as e:
            logger.error(f"Error identifying deductions: {e}")
            return []

    async def _get_recommendations(
        self,
        deductions: list[dict[str, Any]]
    ) -> list[str]:
        """Generate recommendations based on identified deductions."""

        recommendations = []

        for deduction in deductions:
            if deduction.get("deductibility") == "high":
                recommendations.append(
                    f"Include {deduction.get('category')} in Schedule C deductions"
                )
            elif deduction.get("deductibility") == "medium":
                recommendations.append(
                    f"Consult tax professional about {deduction.get('category')} deductibility"
                )

        if not recommendations:
            recommendations.append("Maintain detailed records of all potential expenses")

        return recommendations

    # ── AGT-001 (2026-08-23) ─────────────────────────────────────────────────
    # `_estimate_tax_bracket` deleted. deduction_hunter.py records deleting its
    # own copy under DEM-006, calling it "a FIFTH private copy of the slab
    # table". This was a SIXTH, in a file DEM-006 did not reach, and it carried
    # the same FY 2020-21 values (2.5 / 5 / 7.5 / 10 / 12.5 lakh) into a
    # product computing FY 2026-27 tax under a regime whose basic exemption is
    # ₹4,00,000.
    #
    # That six copies existed is the argument for the rules-as-data design
    # rather than a criticism of whoever wrote the sixth: a slab table that can
    # be typed out is a slab table that will be, and the only durable fix is
    # that there is one place to read it from and no reason to write another.
    # Deleted rather than corrected — a correct private copy is still a copy,
    # and it goes stale the same way in April.
