"""
Deduction Hunter Agent - identifies all possible tax deductions.
Uses user context and knowledge base to suggest deductible expenses.
"""

import logging
import time
from typing import Any

from backend.agents.base_agent import AgentOutput, TaxAgent, confidence_score, derive_confidence
from backend.llm import get_llm

logger = logging.getLogger(__name__)



class DeductionHunterAgent(TaxAgent):
    """
    Identifies potential tax deductions for the user.
    
    Finds:
    - Standard vs itemized deductions
    - Professional expense deductions
    - Home office deductions
    - Education deductions
    - Medical expense deductions
    - Charitable contributions
    - Business expense deductions
    
    Example:
        agent = DeductionHunterAgent()
        result = await agent.execute(
            "I work from home and bought a laptop for work",
            {"employment_type": "freelance", "annual_income": 500000}
        )
    """

    def __init__(self):
        super().__init__("deduction_hunter_agent")

    async def execute(
        self,
        user_query: str,
        user_context: dict[str, Any],
        tools: Any = None,
        **kwargs
    ) -> AgentOutput:
        """Find potential tax deductions for user."""
        start_time = time.time()

        if tools is not None:
            self.set_tools(tools)

        try:
            # Preprocess query
            processed_query = await self.preprocess(user_query)

            # Get user's financial profile
            user_financial_data = {}
            if self.tools:
                user_data = await self.call_tool(
                    "get_user_profile",
                    user_id=user_context.get("user_id", "unknown")
                )
                if user_data.get("success"):
                    res_payload = user_data.get("result", {})
                    if res_payload:
                        user_financial_data = res_payload.get("financial_profile", {})

            # Use real data merged with context for RAG and LLM analysis
            merged_context = {**user_context, **user_financial_data}

            # Get relevant deduction guidelines from knowledge base using tool
            rag_context = ""
            if self.tools:
                rag_result = await self.call_tool(
                    "semantic_search_tax_kb",
                    query=f"tax deductions for {merged_context.get('employment_type', 'individual')}",
                    top_k=5
                )
                if rag_result.get("success"):
                    rag_context = rag_result.get("result", {}).get("context", "")

            # Identify deductions
            deductions = await self._identify_deductions(
                processed_query,
                merged_context,
                rag_context
            )

            # Integrate HRA Exemption tool
            rent_paid = float(user_financial_data.get("rent_paid", 0) or user_financial_data.get("investments", {}).get("rent", 0) or 0)
            if rent_paid > 0 or "rent" in processed_query or "hra" in processed_query:
                annual_income = float(user_financial_data.get("annual_income", 0) or 600000.0)
                basic_salary = float(user_financial_data.get("basic_salary", 0) or (annual_income * 0.40))
                hra_received = float(user_financial_data.get("hra_received", 0) or (basic_salary * 0.50))

                if self.tools:
                    hra_calc = await self.call_tool(
                        "calculate_hra_exemption",
                        basic_salary=basic_salary,
                        hra_received=hra_received,
                        rent_paid=rent_paid or 120000.0,
                        is_metro=any(m in processed_query for m in ["metro", "mumbai", "delhi", "bangalore", "chennai", "kolkata"])
                    )
                    if hra_calc.get("success"):
                        hra_data = hra_calc.get("result", {})
                        if hra_data.get("exempt_hra", 0) > 0:
                            deductions.append({
                                "category": "HRA Exemption",
                                "scheme_code": "10(13A)",
                                "amount": hra_data["exempt_hra"],
                                "confidence": "high",
                                "description": f"Exempt HRA under Section 10(13A). Taxable HRA is ₹{hra_data['taxable_hra']:,.0f}.",
                                "tax_savings": hra_data["exempt_hra"] * 0.20
                            })

            # For each deduction, calculate impact using tool
            total_savings = 0
            for deduction in deductions:
                if self.tools:
                    impact = await self.call_tool(
                        "calculate_deduction_impact",
                        deduction_amount=float(deduction.get("amount", 0)),
                        current_taxable_income=float(user_financial_data.get("annual_income", 0) or user_context.get("annual_income", 0))
                    )
                    deduction["tax_savings"] = impact.get("result", {}).get("tax_savings", 0)
                    total_savings += deduction["tax_savings"]
                else:
                    deduction["tax_savings"] = 0

            # Lookup detailed scheme information
            for deduction in deductions:
                if self.tools and deduction.get("scheme_code"):
                    scheme_info = await self.call_tool(
                        "get_scheme_details",
                        scheme_code=deduction["scheme_code"]
                    )
                    if scheme_info.get("success"):
                        deduction["details"] = scheme_info.get("result", {}).get("details", {})
                        deduction["scheme_details"] = scheme_info.get("result", {}).get("details", {})

            # Calculate total tax impact
            total_tax_liability = 0
            if self.tools:
                total_tax_impact = await self.call_tool(
                    "calculate_tax_liability",
                    total_income=float(user_financial_data.get("annual_income", 0) or user_context.get("annual_income", 0)),
                    deductions=sum(float(d.get("amount", 0)) for d in deductions)
                )
                if total_tax_impact.get("success"):
                    total_tax_liability = total_tax_impact.get("result", {}).get("total_tax_liability", 0)

            # Generate report
            report_data = None
            if self.tools:
                report = await self.call_tool(
                    "generate_tax_report",
                    user_id=user_context.get("user_id", "unknown"),
                    analysis_data={"deductions": deductions}
                )
                if report.get("success"):
                    report_data = report.get("result")

            # Postprocess
            result = {
                "deductions": deductions,
                "deductions_found": deductions,
                "total_deduction_amount": sum(d.get("amount", 0) for d in deductions),
                "total_tax_savings": total_savings,
                "total_tax_liability": total_tax_liability,
                "report": report_data,
                "filing_recommendations": await self._get_filing_recommendations(deductions),
                "documentation_needed": await self._get_documentation_requirements(deductions)
            }

            result = await self.postprocess(result)

            execution_time = (time.time() - start_time) * 1000

            logger.info(f"Found {len(deductions)} potential deductions, total ₹{sum(float(d.get('amount', 0)) for d in deductions):,.0f}")

            return self._create_output(
                result=result,
                status="success",
                confidence=confidence_score(derive_confidence()),
                reasoning="Deductions identified using tool-based verification",
                execution_time_ms=execution_time
            )

        except Exception as e:
            logger.error(f"Error in deduction hunter: {e}")
            execution_time = (time.time() - start_time) * 1000

            return self._create_output(
                result={"error": str(e)},
                status="error",
                confidence=0.0,  # execution failed — not a score
                reasoning=f"Error: {e!s}",
                execution_time_ms=execution_time
            )


    async def _identify_deductions(
        self,
        user_query: str,
        user_context: dict[str, Any],
        rag_context: str
    ) -> list[dict[str, Any]]:
        """Use LLM to identify applicable deductions."""

        employment_type = user_context.get("employment_type", "individual")
        annual_income = user_context.get("annual_income", 0)

        prompt = f"""Identify all possible tax deductions based on the user's situation.

Employment type: {employment_type}
Annual income: ₹{annual_income:,.0f}
User's statement: "{user_query}"

Reference material on deductions:
{rag_context}

For each deduction, provide:
1. Category (Home Office, Equipment, Professional Fees, etc.)
2. Description of the expense
3. Estimated deductible amount (in INR)
4. Deductibility confidence (high/medium/low)
5. Filing requirements
6. Scheme code (e.g. 80C, 80D, 80E, 80TTA, 80TTB, 80CCD, or null if none)

Respond in JSON format:
{{
  "deductions": [
    {{
      "category": "Home Office",
      "description": "30% of home rent for dedicated office space",
      "amount": 180000,
      "confidence": "high",
      "filing_requirement": "Schedule Business income",
      "documentation": "Rental agreement, utility bills",
      "scheme_code": null
    }}
  ]
}}

Important: Only include deductions applicable to the user's situation. Respond ONLY with valid JSON."""

        try:
            from backend.tools.data_validator import LLMResponseValidator
            validator = LLMResponseValidator()

            message = await get_llm().complete(prompt, max_tokens=2000)

            response_text = message.text.strip()

            # Use robust JSON parser with multiple fallback strategies
            response_data, parse_report = validator.parse_json_response(response_text)

            if response_data is None:
                logger.warning(f"Failed to parse deductions JSON: {parse_report.warnings}")
                return []

            raw_deductions = response_data.get("deductions", [])

            # Validate deductions — enforce section limits from ground truth
            validated_deductions, validation_report = validator.validate_deductions(raw_deductions)

            if validation_report.warnings:
                logger.info(f"Deduction validation warnings: {validation_report.warnings}")
            if validation_report.corrections_applied:
                logger.info(f"Deduction corrections applied: {validation_report.corrections_applied}")

            return validated_deductions

        except Exception as e:
            logger.error(f"Error identifying deductions: {e}")
            return []

    async def _get_filing_recommendations(
        self,
        deductions: list[dict[str, Any]]
    ) -> list[str]:
        """Generate filing recommendations based on deductions."""

        recommendations = []

        # Group by filing requirement
        filing_requirements = {}
        for deduction in deductions:
            req = deduction.get("filing_requirement", "ITR")
            if req not in filing_requirements:
                filing_requirements[req] = []
            filing_requirements[req].append(deduction.get("category"))

        for requirement, categories in filing_requirements.items():
            recommendations.append(f"Include these in {requirement}: {', '.join(categories)}")

        # High confidence deductions should be prioritized
        high_confidence = [d for d in deductions if d.get("confidence") == "high"]
        if high_confidence:
            recommendations.append(
                f"Prioritize filing {len(high_confidence)} high-confidence deductions"
            )

        # Documentation warning
        total_deductions = sum(d.get("amount", 0) for d in deductions)
        if total_deductions > 500000:
            recommendations.append(
                "With ₹5+ lakh in deductions, maintain detailed documentation"
            )

        return recommendations

    async def _get_documentation_requirements(
        self,
        deductions: list[dict[str, Any]]
    ) -> dict[str, list[str]]:
        """Get required documentation for each deduction."""

        documentation = {}

        for deduction in deductions:
            category = deduction.get("category", "Other")
            docs = deduction.get("documentation", "").split(",")

            if category not in documentation:
                documentation[category] = []

            documentation[category].extend([d.strip() for d in docs if d.strip()])

        return documentation

    # ── DEM-006 ──────────────────────────────────────────────────────────────
    # `_estimate_tax_bracket` deleted. It held a FIFTH private copy of the slab
    # table, carrying FY 2020-21 values (2.5 / 5 / 7.5 / 10 / 12.5 lakh) into a
    # product computing FY 2026-27 tax.
    #
    # Beyond being stale, the approach was wrong: estimating a deduction's worth
    # as `amount x marginal_rate` breaks wherever the deduction crosses a rebate
    # or surcharge boundary, which is precisely where the figure matters. A
    # ₹2,10,000 employer-NPS contribution on a ₹15,00,000 salary is worth
    # ₹81,900, not the ₹63,000 a marginal-rate estimate would give, because it
    # pulls the taxpayer into the s.87A relief zone.
    #
    # Use the `calculate_deduction_impact` tool, which recomputes tax both ways
    # through backend.core.
