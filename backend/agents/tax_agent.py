"""
Tax deduction agent - identifies deductible expenses and calculates savings.
"""

from typing import Dict, Any
import logging
import time
from groq import Groq

from backend.agents.base_agent import TaxAgent, AgentOutput
from backend.config import settings

logger = logging.getLogger(__name__)

# Initialize Groq client
client = Groq(api_key=settings.llm.api_key)


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
        user_context: Dict[str, Any],
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
            
            # Calculate tax savings
            annual_income = user_context.get("annual_income", 0)
            tax_bracket = self._estimate_tax_bracket(annual_income)
            total_deduction = sum(d.get("amount", 0) for d in deductions)
            estimated_savings = total_deduction * tax_bracket
            
            # Postprocess result
            result = {
                "deductions": deductions,
                "total_deduction_amount": total_deduction,
                "estimated_tax_bracket": tax_bracket,
                "estimated_tax_savings": estimated_savings,
                "recommendations": await self._get_recommendations(deductions)
            }
            
            result = await self.postprocess(result)
            
            execution_time = (time.time() - start_time) * 1000  # Convert to ms
            
            logger.info(f"Tax deduction analysis completed: ${total_deduction} deductions identified")
            
            return self._create_output(
                result=result,
                status="success",
                confidence=0.85,
                reasoning="Identified deductible expenses based on user's situation",
                execution_time_ms=execution_time
            )
        
        except Exception as e:
            logger.error(f"Error in tax deduction agent: {e}")
            execution_time = (time.time() - start_time) * 1000
            
            return self._create_output(
                result={"error": str(e)},
                status="error",
                confidence=0.0,
                reasoning=f"Error during analysis: {str(e)}",
                execution_time_ms=execution_time
            )
    
    async def _identify_deductions(
        self,
        user_query: str,
        user_context: Dict[str, Any]
    ) -> list[Dict[str, Any]]:
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
            message = client.chat.completions.create(
                model=settings.llm.model,
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            response_text = message.choices[0].message.content.strip()
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
        deductions: list[Dict[str, Any]]
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
    
    def _estimate_tax_bracket(self, annual_income: float) -> float:
        """Estimate user's tax bracket (simplified for India)."""
        
        if annual_income <= 250000:
            return 0.0
        elif annual_income <= 500000:
            return 0.05
        elif annual_income <= 750000:
            return 0.10
        elif annual_income <= 1000000:
            return 0.15
        elif annual_income <= 1250000:
            return 0.20
        else:
            return 0.30