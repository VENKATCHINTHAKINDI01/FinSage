"""
Intent detection - analyze user query and determine which agents to invoke.
Uses LLM to understand what the user is asking about.
"""

from enum import Enum
from pydantic import BaseModel
import logging
from typing import Optional
from groq import Groq

from backend.config import settings

logger = logging.getLogger(__name__)

# Define all possible intents
class Intent(str, Enum):
    """User query intents"""
    TAX_DEDUCTION = "tax_deduction"
    TAX_SAVINGS = "tax_savings"
    INVESTMENT_ADVICE = "investment_advice"
    PORTFOLIO_ANALYSIS = "portfolio_analysis"
    GOVERNMENT_BENEFITS = "government_benefits"
    ELIGIBILITY_CHECK = "eligibility_check"
    BUSINESS_EXPENSE = "business_expense"
    FINANCIAL_PLANNING = "financial_planning"
    COMPLIANCE_CHECK = "compliance_check"
    TAX_FILING = "tax_filing"
    TAX_CALCULATION = "tax_calculation"
    CROSS_BORDER_TAX = "cross_border_tax"
    PRICE_INTELLIGENCE = "price_intelligence"
    TAX_STRATEGY = "tax_strategy"
    WEALTH_PLANNING = "wealth_planning"
    GENERAL = "general"


class IntentDetectionResult(BaseModel):
    """Result of intent detection"""
    intent: Intent
    confidence: float  # 0.0 to 1.0
    agents_to_invoke: list[str]  # Which agents should handle this
    reasoning: str  # Why we detected this intent


# Initialize Groq client
client = Groq(api_key=settings.llm.api_key)


async def detect_intent(user_query: str, user_id: str) -> IntentDetectionResult:
    """
    Analyze user query and detect intent.
    
    Args:
        user_query: User's question
        user_id: User making the query
    
    Returns:
        IntentDetectionResult with detected intent and agents to invoke
    
    Example:
        result = await detect_intent("What tax deductions can I claim?", "user-123")
        print(result.intent)  # Intent.TAX_DEDUCTION
        print(result.agents_to_invoke)  # ["tax_agent", "deduction_hunter"]
    """
    
    prompt = f"""Analyze the following user query and determine their intent.
 
User Query: "{user_query}"
 
Classify the intent into ONE of these categories:
1. TAX_DEDUCTION - User asking what expenses they can deduct
2. TAX_SAVINGS - User wanting to know tax savings strategies
3. INVESTMENT_ADVICE - User asking for investment recommendations
4. PORTFOLIO_ANALYSIS - User wanting analysis of their investments
5. GOVERNMENT_BENEFITS - User asking about govt schemes/benefits
6. ELIGIBILITY_CHECK - User checking if they qualify for benefits
7. BUSINESS_EXPENSE - User asking about business expense deductions
8. FINANCIAL_PLANNING - User wanting overall financial planning
9. COMPLIANCE_CHECK - User asking about compliance score, audit readiness, red flags, or missing documents
10. TAX_FILING - User asking about ITR filing, forms, help filing tax, or deadlines
11. TAX_CALCULATION - User asking about complex tax calculations, capital gains, short/long-term gains, loss carry forward, or tax liability estimates
12. CROSS_BORDER_TAX - User asking about NRI rules, residency status Section 6(1), double taxation relief Section 90/91, or foreign assets Schedule FA
13. PRICE_INTELLIGENCE - User asking about Cost Inflation Index (CII), indexation benefits, gold Sovereign Gold Bonds (SGB), or comparing post-tax yield
14. TAX_STRATEGY - User asking about multi-year planning, transitioning old vs new tax regime, or tax harvesting strategies
15. WEALTH_PLANNING - User asking about long-term wealth, NPS retirement withdrawals (60/40), PPF tax-free growth, or capital gains reinvestment Section 54/54EC
16. GENERAL - Query doesn't fit above categories
 
Respond in JSON format:
{{
  "intent": "TAX_DEDUCTION",
  "confidence": 0.95,
  "reasoning": "User explicitly asked about tax deductions for their situation"
}}
 
Important: Respond ONLY with valid JSON, no other text."""

    try:
        message = client.chat.completions.create(
            model=settings.llm.model,
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )
        
        response_text = message.choices[0].message.content.strip()
        
        # Parse JSON response
        import json
        response_data = json.loads(response_text)
        
        intent_str = response_data.get("intent", "GENERAL").upper()
        confidence = float(response_data.get("confidence", 0.5))
        reasoning = response_data.get("reasoning", "Intent detected")
        
        # Map intent to agents
        intent = Intent(intent_str.lower().replace(" ", "_"))
        agents = _get_agents_for_intent(intent)
        
        logger.info(f"Intent detected for user {user_id}: {intent} (confidence: {confidence})")
        
        return IntentDetectionResult(
            intent=intent,
            confidence=confidence,
            agents_to_invoke=agents,
            reasoning=reasoning
        )
    
    except Exception as e:
        logger.error(f"Error detecting intent: {e}")
        # Fallback to GENERAL intent
        return IntentDetectionResult(
            intent=Intent.GENERAL,
            confidence=0.0,
            agents_to_invoke=["income_classifier_agent"],
            reasoning=f"Error during detection: {str(e)}"
        )


def _get_agents_for_intent(intent: Intent) -> list[str]:
    """Map intent to list of agents that should handle it."""
    
    mapping = {
        Intent.TAX_DEDUCTION: ["deduction_hunter_agent", "tax_optimizer_agent"],
        Intent.TAX_SAVINGS: ["tax_optimizer_agent"],
        Intent.INVESTMENT_ADVICE: ["tax_optimizer_agent"],
        Intent.PORTFOLIO_ANALYSIS: ["tax_optimizer_agent"],
        Intent.GOVERNMENT_BENEFITS: ["benefits_discovery_agent"],
        Intent.ELIGIBILITY_CHECK: ["eligibility_verifier_agent"],
        Intent.BUSINESS_EXPENSE: ["income_classifier_agent", "tax_optimizer_agent"],
        Intent.FINANCIAL_PLANNING: ["income_classifier_agent", "tax_optimizer_agent"],
        Intent.COMPLIANCE_CHECK: ["compliance_checker_agent"],
        Intent.TAX_FILING: ["itr_helper_agent"],
        Intent.TAX_CALCULATION: ["advanced_calculator_agent"],
        Intent.CROSS_BORDER_TAX: ["cross_border_tax_agent"],
        Intent.PRICE_INTELLIGENCE: ["price_intelligence_agent"],
        Intent.TAX_STRATEGY: ["tax_strategy_agent"],
        Intent.WEALTH_PLANNING: ["wealth_planner_agent"],
        Intent.GENERAL: ["income_classifier_agent"],
    }
    
    return mapping.get(intent, ["income_classifier_agent"])


class IntentDetector:
    """Wrapper class for intent detection."""
    async def detect_intent(self, user_query: str, user_id: str = "unknown") -> IntentDetectionResult:
        return await detect_intent(user_query, user_id)