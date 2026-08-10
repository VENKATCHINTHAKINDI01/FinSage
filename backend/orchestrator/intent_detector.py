"""
Intent detection - analyze user query and determine which agents to invoke.
Uses LLM to understand what the user is asking about, with keyword-based fallback.
"""

from enum import Enum
from pydantic import BaseModel
import logging
from typing import Optional

from backend.config import settings
from backend.llm import get_llm
from backend.tools.data_validator import LLMResponseValidator

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



# LLM response validator
_llm_validator = LLMResponseValidator()


# ============================================================================
# KEYWORD-BASED FALLBACK INTENT DETECTION
# ============================================================================

_KEYWORD_INTENT_MAP = {
    Intent.TAX_DEDUCTION: [
        "deduction", "deduct", "80c", "80d", "80e", "section 80",
        "hra", "nps", "ppf", "elss", "insurance premium", "deductible"
    ],
    Intent.TAX_SAVINGS: [
        "save tax", "tax saving", "reduce tax", "lower tax", "minimize tax",
        "tax benefit", "tax exemption", "exempt"
    ],
    Intent.INVESTMENT_ADVICE: [
        "invest", "mutual fund", "stock", "share", "sip", "portfolio",
        "where to invest", "best investment", "returns"
    ],
    Intent.PORTFOLIO_ANALYSIS: [
        "portfolio", "holdings", "asset allocation", "diversify", "rebalance"
    ],
    Intent.GOVERNMENT_BENEFITS: [
        "government scheme", "govt scheme", "benefit", "subsidy", "yojana",
        "pradhan mantri", "jan dhan", "pmjdy", "sukanya"
    ],
    Intent.ELIGIBILITY_CHECK: [
        "eligible", "eligibility", "qualify", "can i claim", "am i eligible"
    ],
    Intent.BUSINESS_EXPENSE: [
        "business expense", "office expense", "professional expense",
        "freelance expense", "work from home", "home office"
    ],
    Intent.FINANCIAL_PLANNING: [
        "financial plan", "retirement", "goal", "budget", "savings plan",
        "long term plan", "financial future"
    ],
    Intent.COMPLIANCE_CHECK: [
        "compliance", "audit", "red flag", "scrutiny", "notice",
        "missing document", "tax notice", "penalty"
    ],
    Intent.TAX_FILING: [
        "itr", "file tax", "tax return", "form 16", "filing",
        "deadline", "e-file", "26as", "tax filing"
    ],
    Intent.TAX_CALCULATION: [
        "calculate tax", "tax calculator", "capital gains", "short term",
        "long term gain", "stcg", "ltcg", "loss carry", "tax liability"
    ],
    Intent.CROSS_BORDER_TAX: [
        "nri", "foreign", "residency", "double tax", "dtaa",
        "overseas", "international", "foreign asset", "schedule fa"
    ],
    Intent.PRICE_INTELLIGENCE: [
        "cost inflation", "cii", "indexation", "gold price", "sgb",
        "post-tax yield", "sovereign gold"
    ],
    Intent.TAX_STRATEGY: [
        "strategy", "old regime", "new regime", "regime comparison",
        "tax harvesting", "multi-year", "tax planning strategy"
    ],
    Intent.WEALTH_PLANNING: [
        "wealth", "nps withdrawal", "ppf maturity", "section 54",
        "reinvestment", "capital gains reinvest", "long term wealth"
    ],
}


def _detect_intent_by_keywords(query: str) -> IntentDetectionResult:
    """Fallback intent detection using keyword matching."""
    query_lower = query.lower()
    
    best_intent = Intent.GENERAL
    best_score = 0
    best_keywords = []
    
    for intent, keywords in _KEYWORD_INTENT_MAP.items():
        matches = [kw for kw in keywords if kw in query_lower]
        score = len(matches)
        if score > best_score:
            best_score = score
            best_intent = intent
            best_keywords = matches
    
    confidence = min(0.7, 0.3 + (best_score * 0.15))  # Cap keyword-based confidence at 0.7
    agents = _get_agents_for_intent(best_intent)
    
    return IntentDetectionResult(
        intent=best_intent,
        confidence=confidence,
        agents_to_invoke=agents,
        reasoning=f"Keyword match: {', '.join(best_keywords)}" if best_keywords else "No keyword match — defaulting to general"
    )


# ============================================================================
# LLM-BASED INTENT DETECTION
# ============================================================================

async def detect_intent(user_query: str, user_id: str) -> IntentDetectionResult:
    """
    Analyze user query and detect intent.
    Uses LLM with keyword-based fallback.
    
    Args:
        user_query: User's question
        user_id: User making the query
    
    Returns:
        IntentDetectionResult with detected intent and agents to invoke
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
        message = await get_llm().complete(prompt, max_tokens=200)
        
        response_text = message.text.strip()
        
        # Use robust JSON parser
        response_data, parse_report = _llm_validator.parse_json_response(response_text)
        
        if response_data is None:
            # JSON parse failed — fall back to keyword detection
            logger.warning(f"LLM intent JSON parse failed for user {user_id}, using keyword fallback")
            return _detect_intent_by_keywords(user_query)
        
        # Validate the parsed response
        validated_data, validation_report = _llm_validator.validate_intent_response(response_data)
        
        intent_str = validated_data.get("intent", "GENERAL").upper()
        confidence = float(validated_data.get("confidence", 0.5))
        reasoning = validated_data.get("reasoning", "Intent detected")
        
        # If LLM confidence is too low, supplement with keyword detection
        if confidence < 0.5:
            keyword_result = _detect_intent_by_keywords(user_query)
            if keyword_result.confidence > confidence:
                logger.info(f"LLM confidence low ({confidence}), using keyword result ({keyword_result.confidence})")
                return keyword_result
        
        # Map intent to agents
        try:
            intent = Intent(intent_str.lower().replace(" ", "_"))
        except ValueError:
            logger.warning(f"Invalid intent value '{intent_str}', defaulting to GENERAL")
            intent = Intent.GENERAL
            
        agents = _get_agents_for_intent(intent)
        
        logger.info(f"Intent detected for user {user_id}: {intent} (confidence: {confidence})")
        
        return IntentDetectionResult(
            intent=intent,
            confidence=confidence,
            agents_to_invoke=agents,
            reasoning=reasoning
        )
    
    except Exception as e:
        logger.error(f"Error detecting intent via LLM: {e}")
        # Fallback to keyword-based detection instead of empty result
        keyword_result = _detect_intent_by_keywords(user_query)
        logger.info(f"Using keyword fallback: {keyword_result.intent} (confidence: {keyword_result.confidence})")
        return keyword_result


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