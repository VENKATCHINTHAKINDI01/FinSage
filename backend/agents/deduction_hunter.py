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
            # `merged_context`, not `user_financial_data`. These lookups read
            # only the stored profile, so a user who stated their rent, basic
            # salary or HRA in the request had it silently ignored — and then
            # got the invented figures below instead of their own. Merged
            # context is profile-over-context, so a saved profile still wins;
            # what changes is that stating a figure now has an effect.
            rent_paid = float(merged_context.get("rent_paid", 0) or merged_context.get("investments", {}).get("rent", 0) or 0)
            if rent_paid > 0 or "rent" in processed_query or "hra" in processed_query:
                # AGT-001. This used to invent the user's entire payslip when
                # it did not know it: annual income defaulted to ₹6,00,000,
                # basic salary to 40% of that, HRA received to 50% of basic,
                # and rent to ₹1,20,000. None of those are tax rules — they
                # are guesses about a document the agent has not seen.
                #
                # The result was worse than a bare guess. The s.10(13A)
                # exemption is the LEAST of three amounts, two of which are
                # basic-salary-derived, so feeding invented inputs to the real
                # engine produced an invented answer WITH A WORKSHEET
                # attached, which reads as more trustworthy than a number
                # somebody obviously made up.
                #
                # So a missing input now produces a stated gap. HRA is the one
                # deduction where the user always has the figures to hand —
                # they are on the payslip — so asking is cheap and guessing is
                # not.
                basic_salary = float(merged_context.get("basic_salary", 0) or 0)
                hra_received = float(merged_context.get("hra_received", 0) or 0)
                missing = [
                    label for label, value in (
                        ("basic salary", basic_salary),
                        ("HRA received", hra_received),
                        ("rent paid", rent_paid),
                    ) if not value
                ]
                if missing:
                    deductions.append({
                        "category": "HRA Exemption",
                        "scheme_code": "10(13A)",
                        "amount": None,
                        "amount_known": False,
                        "confidence": "unknown",
                        "description": (
                            "HRA exemption under s.10(13A) is the least of "
                            "three amounts, so it cannot be estimated without "
                            + ", ".join(missing)
                            + ". These are on your payslip."
                        ),
                    })
                elif self.tools:
                    hra_calc = await self.call_tool(
                        "calculate_hra_exemption",
                        basic_salary=basic_salary,
                        hra_received=hra_received,
                        # Reached only when all three inputs are known, so
                        # there is no `or 120000.0` default left to apply.
                        rent_paid=rent_paid,
                        is_metro=any(m in processed_query for m in ["metro", "mumbai", "delhi", "bangalore", "chennai", "kolkata"])
                    )
                    if hra_calc.get("success"):
                        hra_data = hra_calc.get("result", {})
                        # Pre-existing bug: exempt_hra/taxable_hra are decimal
                        # STRINGS (Money.to_json()), not floats. `> 0` on a str
                        # raises TypeError, and so does the :,.0f format below
                        # — this whole branch crashed with a real (non-mocked)
                        # calculate_hra_exemption result on every path,
                        # whenever a user actually had rent_paid > 0.
                        exempt_hra = float(hra_data.get("exempt_hra", 0) or 0)
                        taxable_hra = float(hra_data.get("taxable_hra", 0) or 0)
                        if exempt_hra > 0:
                            deductions.append({
                                "category": "HRA Exemption",
                                "scheme_code": "10(13A)",
                                "amount": exempt_hra,
                                "confidence": "high",
                                "description": f"Exempt HRA under Section 10(13A). Taxable HRA is ₹{taxable_hra:,.0f}.",
                                # AGT-001 bugfix: this carried a flat *0.20 guess
                                # here, immediately overwritten by the real
                                # calculate_deduction_impact call below on every
                                # path — dead, misleading arithmetic rather than
                                # a live bug, but exactly the pattern this pass
                                # is removing wherever found. tax_savings is set
                                # once, below, from the deterministic tool.
                            })

            # For each deduction, calculate impact using tool. A deduction
            # with no stated amount (amount_known is False — see
            # _identify_deductions) gets no tax_savings figure at all rather
            # than one computed from an LLM-guessed amount.
            total_savings = 0
            for deduction in deductions:
                if deduction.get("amount_known") is False:
                    deduction["tax_savings"] = None
                    continue
                if self.tools:
                    impact = await self.call_tool(
                        "calculate_deduction_impact",
                        deduction_amount=float(deduction.get("amount", 0)),
                        current_taxable_income=float(user_financial_data.get("annual_income", 0) or user_context.get("annual_income", 0))
                    )
                    # Pre-existing bug, unrelated to amount_known: tax_savings
                    # is a decimal STRING (Money.to_json()), so the += below
                    # raised TypeError the first time this path actually ran
                    # end to end. Never caught because nothing exercised it
                    # with self.tools set.
                    deduction["tax_savings"] = float(impact.get("result", {}).get("tax_savings", 0))
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
                    deductions=sum(float(d.get("amount") or 0) for d in deductions)
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
                "total_deduction_amount": sum(d.get("amount") or 0 for d in deductions if d.get("amount_known") is not False),
                "total_tax_savings": total_savings,
                "total_tax_liability": total_tax_liability,
                "amount_needed_from_user": [
                    d.get("category", "deduction") for d in deductions if d.get("amount_known") is False
                ],
                "report": report_data,
                "filing_recommendations": await self._get_filing_recommendations(deductions),
                "documentation_needed": await self._get_documentation_requirements(deductions)
            }

            result = await self.postprocess(result)

            execution_time = (time.time() - start_time) * 1000

            logger.info(f"Found {len(deductions)} potential deductions, total ₹{sum(float(d.get('amount') or 0) for d in deductions):,.0f}")

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
3. Amount (in INR) — ONLY if the user's statement gives you a real figure to
   work from (an amount they mentioned, or a fixed statutory limit like
   80C's ₹1,50,000). If neither is present, set "amount" to null and
   "amount_known" to false — do NOT estimate a plausible-sounding figure.
   A guess presented as a number is worse than admitting you don't know it.
4. Deductibility confidence (high/medium/low)
5. Filing requirements
6. Scheme code (e.g. 80C, 80D, 80E, 80TTA, 80TTB, 80CCD, or null if none)

Respond in JSON format:
{{
  "deductions": [
    {{
      "category": "Section 80C investments",
      "description": "ELSS, PPF, life insurance premiums etc., up to the statutory limit",
      "amount": 150000,
      "amount_known": true,
      "confidence": "high",
      "filing_requirement": "Schedule VI-A",
      "documentation": "Investment receipts",
      "scheme_code": "80C"
    }},
    {{
      "category": "Home Office",
      "description": "A share of home rent/utilities for a dedicated office space — the user did not state how much they spend",
      "amount": null,
      "amount_known": false,
      "confidence": "medium",
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
        total_deductions = sum(d.get("amount") or 0 for d in deductions)
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
