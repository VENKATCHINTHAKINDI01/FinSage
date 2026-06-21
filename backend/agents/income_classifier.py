"""
Income Classifier Agent - analyzes user's income sources and structures.
Categorizes income into salary, freelance, passive, investments, etc.
"""

import time
import logging
from typing import Dict, Any
from groq import Groq

from backend.agents.base_agent import TaxAgent, AgentOutput
from backend.config import settings

logger = logging.getLogger(__name__)

# Initialize Groq client
client = Groq(api_key=settings.llm.api_key)


class IncomeClassifierAgent(TaxAgent):
    """
    Analyzes and classifies user income sources.
    
    Identifies:
    - Salary/employment income
    - Freelance/contract income
    - Business/self-employment income
    - Passive income (rental, dividends)
    - Investment income (capital gains)
    - Other income sources
    
    Example:
        agent = IncomeClassifierAgent()
        result = await agent.execute(
            "I earn a salary of 80 lakhs and have rental income of 5 lakhs",
            {"annual_income": 850000}
        )
    """
    
    def __init__(self):
        super().__init__("income_classifier_agent")
    
    async def execute(
        self,
        user_query: str,
        user_context: Dict[str, Any],
        tools: Any = None,
        **kwargs
    ) -> AgentOutput:
        """Analyze income sources using tools."""
        start_time = time.time()
        
        if tools is not None:
            self.set_tools(tools)
            
        try:
            # Preprocess query
            processed_query = await self.preprocess(user_query)
            
            # Get actual user financial data / profile
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
            
            # Use real data merged with context for LLM analysis
            merged_context = {**user_context, **user_financial_data}
            
            # Extract income sources using LLM
            income_sources = await self._extract_income_sources(
                processed_query,
                merged_context
            )
            
            # Fetch Form 26AS to verify and supplement income sources
            if self.tools:
                form26as = await self.call_tool(
                    "fetch_form_26as_statement",
                    pan_number=user_context.get("pan", "ABCDE1234F")
                )
                if form26as.get("success"):
                    credits = form26as.get("result", {}).get("tds_deducted", [])
                    for credit in credits:
                        credit_amount = credit["amount_paid"]
                        if not any(abs(src.get("amount", 0) - credit_amount) < 100 for src in income_sources):
                            income_sources.append({
                                "type": "Salary" if "salary" in credit["section"].lower() else "Interest",
                                "amount": credit_amount,
                                "source_name": credit["deductor_name"],
                                "regularity": "regular",
                                "tax_filing": f"Verified via Form 26AS Section {credit['section']}"
                            })

            # Calculate Professional Tax implications
            has_salary = any(src.get("type", "").lower() == "salary" for src in income_sources)
            professional_tax_deduction = 0.0
            if has_salary and self.tools:
                pt_calc = await self.call_tool(
                    "calculate_professional_tax",
                    state=user_context.get("state", "Maharashtra"),
                    monthly_income=float(user_financial_data.get("annual_income", 0) or sum(src.get("amount", 0) for src in income_sources)) / 12.0
                )
                if pt_calc.get("success"):
                    professional_tax_deduction = pt_calc.get("result", {}).get("annual_professional_tax", 0)
            
            # Calculate tax implications using tools
            for source in income_sources:
                if self.tools:
                    impact = await self.call_tool(
                        "calculate_deduction_impact",
                        deduction_amount=float(source.get("amount", 0)),
                        current_taxable_income=float(user_financial_data.get("annual_income", 0) or user_context.get("annual_income", 0))
                    )
                    source["tax_impact"] = impact.get("result", {}).get("tax_savings", 0)
                else:
                    source["tax_impact"] = 0
            
            # Calculate totals
            total_income = sum(src.get("amount", 0) for src in income_sources)
            
            result = {
                "income_sources": income_sources,
                "total_income": total_income,
                "professional_tax_deduction": professional_tax_deduction,
                "income_composition": await self._analyze_composition(income_sources),
                "tax_implications": await self._get_tax_implications(income_sources)
            }
            
            # Save analysis
            if self.tools:
                await self.call_tool(
                    "save_analysis",
                    user_id=user_context.get("user_id", "unknown"),
                    analysis_type="income_analysis",
                    analysis_data=result,
                    agent_name=self.name
                )
            
            result = await self.postprocess(result)
            
            execution_time = (time.time() - start_time) * 1000
            
            logger.info(f"Income classified: {len(income_sources)} sources, total ₹{total_income:,.0f}")
            
            return self._create_output(
                result=result,
                status="success",
                confidence=0.85,
                reasoning="Income sources identified and analyzed using tools",
                execution_time_ms=execution_time
            )
        
        except Exception as e:
            logger.error(f"Error in income classifier: {e}")
            execution_time = (time.time() - start_time) * 1000
            
            return self._create_output(
                result={"error": str(e)},
                status="error",
                confidence=0.0,
                reasoning=f"Error: {str(e)}",
                execution_time_ms=execution_time
            )
    
    
    async def _extract_income_sources(
        self,
        user_query: str,
        user_context: Dict[str, Any]
    ) -> list[Dict[str, Any]]:
        """Use LLM to identify and classify income sources from user query."""
        
        prompt = f"""Analyze the user's income sources and classify them.

User's statement: "{user_query}"

Identify all income sources mentioned. For each, provide:
1. Source type (Salary, Freelance, Business, Rental, Investments, Other)
2. Estimated annual amount (in INR)
3. Regularity (Regular/Irregular)
4. Tax characteristics

Respond in JSON format:
{{
  "income_sources": [
    {{
      "type": "Salary",
      "amount": 800000,
      "source_name": "Primary job at Tech Corp",
      "regularity": "regular",
      "tax_filing": "Form 16 from employer"
    }},
    {{
      "type": "Freelance",
      "amount": 200000,
      "source_name": "Consulting projects",
      "regularity": "irregular",
      "tax_filing": "Schedule Business income"
    }}
  ]
}}

Important: Respond ONLY with valid JSON."""

        try:
            message = client.chat.completions.create(
                model=settings.llm.model,
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}]
            )
            
            response_text = message.choices[0].message.content.strip()
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            import json
            response_data = json.loads(response_text)
            
            return response_data.get("income_sources", [])
        
        except Exception as e:
            logger.error(f"Error extracting income sources: {e}")
            return []
    
    async def _analyze_composition(
        self,
        income_sources: list[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Analyze income composition (percentage breakdown by type)."""
        
        total = sum(src.get("amount", 0) for src in income_sources)
        if total == 0:
            return {}
        
        composition = {}
        for source in income_sources:
            source_type = source.get("type", "Other")
            amount = source.get("amount", 0)
            percentage = (amount / total) * 100
            
            if source_type not in composition:
                composition[source_type] = {
                    "amount": 0,
                    "percentage": 0,
                    "count": 0
                }
            
            composition[source_type]["amount"] += amount
            composition[source_type]["percentage"] = (composition[source_type]["amount"] / total) * 100
            composition[source_type]["count"] += 1
        
        return composition
    
    async def _get_tax_implications(
        self,
        income_sources: list[Dict[str, Any]]
    ) -> list[str]:
        """Generate tax implications based on income sources."""
        
        implications = []
        
        for source in income_sources:
            source_type = source.get("type", "Other")
            amount = source.get("amount", 0)
            
            if source_type == "Salary":
                if amount > 500000:
                    implications.append("High salary may put you in higher tax bracket")
                implications.append("Employer should file Form 16 for tax compliance")
            
            elif source_type == "Freelance":
                implications.append("Freelance income must be reported in Schedule Business")
                implications.append("Eligible for professional deductions (office, equipment, etc)")
            
            elif source_type == "Business":
                implications.append("Self-employed: must file income tax return")
                implications.append("Eligible for business-related expense deductions")
                implications.append("Consider quarterly estimated tax payments")
            
            elif source_type == "Rental":
                implications.append("Rental income subject to tax (even if not received)")
                implications.append("Eligible for property depreciation and maintenance deductions")
            
            elif source_type == "Investments":
                implications.append("Capital gains tax applies (short-term vs long-term rates)")
                implications.append("Dividend income may qualify for dividend tax credit")
        
        return implications