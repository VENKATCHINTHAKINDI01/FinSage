"""
Step 8.1: Benefits Discovery Agent
==================================

Discover government schemes user qualifies for.
"""

import logging
import time
from typing import Any

from backend.agents.base_agent import AgentOutput, TaxAgent, confidence_score, derive_confidence

logger = logging.getLogger(__name__)


class BenefitsDiscoveryAgent(TaxAgent):
    """
    Discover applicable government benefits/schemes.
    
    • Analyzes user profile
    • Matches against scheme database
    • Returns eligibility + benefits
    • Calculates potential savings
    """

    def __init__(self):
        super().__init__("benefits_discovery_agent", "government_benefits")

    async def execute(
        self,
        user_query: str,
        user_context: dict[str, Any],
        tools=None,
        **kwargs
    ) -> AgentOutput:
        """
        Discover benefits.
        
        Workflow:
          1. Get user profile
          2. Analyze eligibility
          3. Lookup schemes
          4. Calculate benefits
          5. Return recommendations
        """
        start_time = time.time()

        if tools is not None:
            self.set_tools(tools)

        try:
            self.logger.info(f"Starting benefits discovery for user {user_context.get('user_id')}")

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

            # Resolve age, employment_type, health_insurance, and education_loan
            age = basic_info.get("age") or user_context.get("age") or 35
            employment_type = basic_info.get("employment_type") or user_context.get("employment_type") or "salaried"

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

            # STEP 1: Get scheme eligibility
            if self.tools:
                applicable = await self.call_tool(
                    "get_applicable_schemes",
                    age=age,
                    employment_type=employment_type,
                    has_health_insurance=has_health_insurance,
                    has_education_loan=has_education_loan
                )

                schemes = applicable.get("result", {}).get("applicable_schemes", [])
            else:
                schemes = []

            # STEP 2: Get details for each scheme
            scheme_details = []
            for scheme in schemes:
                if self.tools:
                    details = await self.call_tool(
                        "get_scheme_details",
                        scheme_code=scheme.get("code", "")
                    )

                    scheme_info = {
                        "code": scheme.get("code"),
                        "name": scheme.get("name"),
                        "limit": scheme.get("limit"),
                        "description": details.get("result", {}).get("description", ""),
                        "benefits": details.get("result", {}).get("benefits", []),
                        "eligibility": scheme.get("recommendation_strength"),
                        "documents_needed": details.get("result", {}).get("documents_needed", [])
                    }
                    scheme_details.append(scheme_info)

            # STEP 3: Categorize schemes
            categories = self._categorize_schemes(scheme_details)

            # STEP 4: Calculate potential savings.
            #
            # AGT-001 bugfix. This was `limit * 0.2` applied to every scheme's
            # limit regardless of what kind of scheme it was — for a Chapter
            # VI-A deduction (80C, 80D, ...) that is a flat-rate guess with the
            # same problem `calculate_deduction_impact` exists to avoid (wrong
            # wherever a rebate or surcharge boundary is crossed); for a loan
            # or insurance scheme, "limit" is not a deduction amount at all —
            # e.g. a home-loan scheme's limit is the loan ceiling, and ×0.2
            # of a ₹35,00,000 ceiling produced a nonsensical "₹7,00,000
            # potential savings". Only Chapter VI-A schemes (code starts with
            # "80") get a real, tool-computed savings figure; everything else
            # gets none rather than a wrong one.
            annual_income = float(
                financial_profile.get("annual_income", 0) or user_context.get("annual_income", 0)
            )
            total_potential = 0.0
            if self.tools and annual_income > 0:
                for scheme in scheme_details:
                    limit = scheme.get("limit")
                    code = str(scheme.get("code", ""))
                    if not (code.startswith("80") and isinstance(limit, (int, float)) and limit > 0):
                        scheme["potential_savings"] = None
                        continue
                    impact = await self.call_tool(
                        "calculate_deduction_impact",
                        deduction_amount=float(limit),
                        current_taxable_income=annual_income,
                    )
                    # calculate_deduction_impact returns tax_savings as a decimal
                    # STRING (Money.to_json() — deliberately never a JSON number,
                    # to avoid float round-tripping through IEEE754), not a float.
                    raw_savings = impact.get("result", {}).get("tax_savings") if impact.get("success") else None
                    savings = float(raw_savings) if raw_savings is not None else None
                    scheme["potential_savings"] = savings
                    if savings:
                        total_potential += savings
            else:
                for scheme in scheme_details:
                    scheme["potential_savings"] = None

            result = {
                "schemes_found": len(scheme_details),
                "scheme_details": scheme_details,
                "categories": categories,
                "total_potential_savings": total_potential,
                "top_recommendations": self._rank_schemes(scheme_details)[:3],
                "action_items": self._generate_action_items(scheme_details),
                "next_steps": self._get_next_steps(scheme_details)
            }

            execution_time = (time.time() - start_time) * 1000

            return self._create_output(
                result=result,
                status="success",
                confidence=confidence_score(derive_confidence()),
                reasoning="Government benefits/schemes discovered based on user context",
                execution_time_ms=execution_time
            )

        except Exception as e:
            self.logger.error(f"Error in benefits discovery: {e}", exc_info=True)
            execution_time = (time.time() - start_time) * 1000

            return self._create_output(
                result={"error": str(e)},
                status="error",
                confidence=0.0,  # execution failed — not a score
                reasoning=f"Error: {e!s}",
                execution_time_ms=execution_time
            )

    def _categorize_schemes(self, schemes: list[dict]) -> dict[str, list[str]]:
        """Categorize schemes."""
        categories = {}

        for scheme in schemes:
            # Categorize by benefit type
            code = scheme.get("code", "")

            if code.startswith("80"):
                cat = "Tax Deductions"
            elif "Insurance" in scheme.get("name", ""):
                cat = "Insurance"
            elif "Loan" in scheme.get("name", ""):
                cat = "Loans"
            else:
                cat = "Other Benefits"

            if cat not in categories:
                categories[cat] = []

            categories[cat].append(scheme.get("name", "Unknown"))

        return categories

    def _rank_schemes(self, schemes: list[dict]) -> list[dict]:
        """Rank schemes by potential benefit."""
        # Sort by limit (potential benefit)
        ranked = sorted(
            schemes,
            key=lambda x: x.get("limit", 0),
            reverse=True
        )

        return ranked

    def _generate_action_items(self, schemes: list[dict]) -> list[str]:
        """Generate action items."""
        actions = []

        # High priority schemes
        high_priority = [s for s in schemes if s.get("limit", 0) > 100000]
        if high_priority:
            actions.append(f"Apply for {len(high_priority)} high-benefit schemes immediately")

        # Document requirements
        all_docs = set()
        for scheme in schemes:
            all_docs.update(scheme.get("documents_needed", []))

        if all_docs:
            actions.append(f"Gather {len(all_docs)} documents needed across schemes")

        # Deadline warnings
        actions.append("Check scheme application deadlines (often year-end)")

        return actions

    def _get_next_steps(self, schemes: list[dict]) -> list[str]:
        """Get next steps."""
        steps = [
            "1. Review recommended schemes above",
            "2. Gather required documents",
            "3. Visit official government portal",
            "4. Submit applications",
            "5. Track application status"
        ]

        return steps
