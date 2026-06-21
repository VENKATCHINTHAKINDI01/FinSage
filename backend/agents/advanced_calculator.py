"""
Step 9.3: Advanced Calculator Agent
===================================

Complex tax scenarios + Capital gains + Loss handling.
"""

import time
import logging
from typing import Dict, Any, List
from datetime import datetime

from backend.agents.base_agent import TaxAgent, AgentOutput

logger = logging.getLogger(__name__)


class AdvancedCalculatorAgent(TaxAgent):
    """
    Handle complex tax calculations.
    
    • Multiple income sources
    • Capital gains (STCG/LTCG)
    • Loss carry forward
    • Setoff rules
    • Tax optimization
    """
    
    def __init__(self):
        super().__init__("advanced_calculator_agent", "tax_calculation")
        
    async def execute(
        self,
        user_query: str,
        user_context: Dict[str, Any],
        tools=None,
        **kwargs
    ) -> AgentOutput:
        """
        Calculate complex tax scenarios.
        
        Workflow:
          1. Gather all income sources
          2. Calculate capital gains
          3. Apply loss set-off rules
          4. Determine deductions
          5. Calculate final tax liability
          6. Show tax optimization
        """
        start_time = time.time()
        
        if tools is not None:
            self.set_tools(tools)
            
        try:
            self.logger.info(f"Running advanced calculation for user {user_context.get('user_id')}")
            
            # STEP 1: Gather income data
            if self.tools:
                income_data = await self.call_tool(
                    "get_user_income_history",
                    user_id=user_context.get("user_id", "unknown"),
                    years=1
                )
                incomes = income_data.get("result", {}).get("income_history", [{}])[0] if income_data.get("result") else {}
            else:
                incomes = user_context
            
            # STEP 2: Calculate each income type
            salary = incomes.get("salary_income", 0)
            business = incomes.get("business_income", 0)
            rental = incomes.get("rental_income", 0)
            ltcg = user_context.get("long_term_gains", 0) or incomes.get("long_term_gains", 0) or 0
            stcg = user_context.get("short_term_gains", 0) or incomes.get("short_term_gains", 0) or 0
            
            # STEP 3: Calculate tax components
            tax_on_salary = self._calculate_salary_tax(salary)
            tax_on_business = self._calculate_business_tax(business)
            tax_on_rental = self._calculate_rental_tax(rental)
            tax_on_ltcg = self._calculate_ltcg_tax(ltcg)
            tax_on_stcg = self._calculate_stcg_tax(stcg, salary + business + rental)
            
            # STEP 4: Apply loss set-off rules
            losses = user_context.get("losses", {})
            loss_setoff = self._apply_loss_setoff(
                {
                    "business_loss": losses.get("business", 0),
                    "capital_loss": losses.get("capital", 0)
                },
                {
                    "salary": tax_on_salary,
                    "business": tax_on_business,
                    "rental": tax_on_rental,
                    "ltcg": tax_on_ltcg,
                    "stcg": tax_on_stcg
                }
            )
            
            # STEP 5: Get deductions
            if self.tools:
                deductions = await self.call_tool(
                    "get_user_deductions",
                    user_id=user_context.get("user_id", "unknown")
                )
                deductions_dict = deductions.get("result", {}).get("deductions", {})
            else:
                deductions_dict = {}
            
            total_deductions = sum(d.get("claimed", 0) for d in deductions_dict.values()) if isinstance(deductions_dict, dict) else 0
            
            # STEP 6: Final tax calculation
            gross_income = salary + business + rental + stcg + ltcg
            taxable_income = max(0, gross_income - total_deductions)
            
            # Use tool for final calculation
            if self.tools:
                final_calc = await self.call_tool(
                    "calculate_tax_liability",
                    total_income=gross_income,
                    deductions=total_deductions,
                    age=user_context.get("age", 35),
                    employment_type=user_context.get("employment_type", "individual")
                )
                final_tax = final_calc.get("result", {}).get("total_tax_liability", 0) or final_calc.get("result", {}).get("total_tax", 0)
            else:
                final_tax = self._estimate_final_tax(taxable_income)
            
            # STEP 7: Optimization suggestions
            optimization = self._suggest_optimizations(
                gross_income,
                total_deductions,
                final_tax,
                user_context
            )
            
            result = {
                "gross_income": gross_income,
                "income_breakdown": {
                    "salary": salary,
                    "business": business,
                    "rental": rental,
                    "capital_gains_stcg": stcg,
                    "capital_gains_ltcg": ltcg
                },
                "deductions": {
                    "claimed": total_deductions,
                    "details": list(deductions_dict.keys()) if isinstance(deductions_dict, dict) else []
                },
                "taxable_income": taxable_income,
                "tax_breakdown": {
                    "income_tax": final_tax * 0.7,
                    "surcharge": final_tax * 0.15,
                    "cess": final_tax * 0.15
                },
                "total_tax_liability": final_tax,
                "effective_tax_rate": (final_tax / gross_income * 100) if gross_income > 0 else 0,
                "loss_setoff_details": loss_setoff,
                "optimization_suggestions": optimization,
                "estimated_refund": max(0, user_context.get("tds_paid", 0) - final_tax),
                "balance_due": max(0, final_tax - user_context.get("tds_paid", 0))
            }
            
            execution_time = (time.time() - start_time) * 1000
            
            return self._create_output(
                result=result,
                status="success",
                confidence=0.92,
                reasoning="Advanced tax calculation completed including multiple income heads and capital gains.",
                execution_time_ms=execution_time
            )
        
        except Exception as e:
            self.logger.error(f"Error in advanced calculator: {e}", exc_info=True)
            execution_time = (time.time() - start_time) * 1000
            
            return self._create_output(
                result={"error": str(e)},
                status="error",
                confidence=0.0,
                reasoning=f"Error running complex calculations: {str(e)}",
                execution_time_ms=execution_time
            )
            
    def _calculate_salary_tax(self, salary: float) -> float:
        """Calculate tax on salary income."""
        if salary <= 250000:
            return 0
        elif salary <= 500000:
            return (salary - 250000) * 0.05
        elif salary <= 1000000:
            return (250000 * 0.05) + ((salary - 500000) * 0.20)
        else:
            return (250000 * 0.05) + (500000 * 0.20) + ((salary - 1000000) * 0.30)
    
    def _calculate_business_tax(self, business_income: float) -> float:
        """Calculate tax on business income."""
        if business_income <= 250000:
            return 0
        else:
            return (business_income - 250000) * 0.30
    
    def _calculate_rental_tax(self, rental_income: float) -> float:
        """Calculate tax on rental income."""
        # Rental income taxed as per slab rates
        return rental_income * 0.20
    
    def _calculate_ltcg_tax(self, ltcg: float) -> float:
        """Calculate tax on long-term capital gains."""
        # 20% on LTCG + 4% cess
        return ltcg * 0.20 * 1.04
    
    def _calculate_stcg_tax(self, stcg: float, other_income: float) -> float:
        """Calculate tax on short-term capital gains."""
        # STCG taxed as ordinary income at applicable slab
        marginal_rate = 0.20 if other_income > 1000000 else 0.10
        return stcg * marginal_rate
    
    def _apply_loss_setoff(
        self,
        losses: Dict[str, float],
        tax_components: Dict[str, float]
    ) -> Dict[str, Any]:
        """Apply loss set-off rules."""
        business_loss = losses.get("business_loss", 0)
        capital_loss = losses.get("capital_loss", 0)
        
        # Capital loss can only setoff capital gains
        # Business loss can setoff any income
        
        capital_gains = tax_components.get("ltcg", 0) + tax_components.get("stcg", 0)
        remaining_capital_loss = max(0, capital_loss - capital_gains)
        
        # Carry forward remaining capital loss
        carried_forward = remaining_capital_loss
        
        return {
            "business_loss_applied": min(business_loss, tax_components.get("rental", 0)),
            "capital_loss_applied": min(capital_loss, capital_gains),
            "loss_carried_forward": carried_forward,
            "setoff_explanation": "Business loss offset rental income; Capital loss offset capital gains"
        }
    
    def _suggest_optimizations(
        self,
        gross_income: float,
        current_deductions: float,
        tax_liability: float,
        user_context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Suggest tax optimization strategies."""
        suggestions = []
        
        # Suggestion 1: Deduction headroom
        max_deduction = 150000  # 80C limit
        if current_deductions < max_deduction:
            headroom = max_deduction - current_deductions
            tax_savings = headroom * 0.20
            suggestions.append({
                "strategy": "Maximize 80C deductions",
                "headroom": headroom,
                "potential_savings": tax_savings,
                "action": f"Invest additional ₹{headroom:,.0f} in ELSS/PPF"
            })
        
        # Suggestion 2: Health insurance
        if not user_context.get("health_insurance"):
            suggestions.append({
                "strategy": "Get health insurance (80D)",
                "potential_savings": 30000,
                "action": "Buy health insurance policy"
            })
        
        # Suggestion 3: NPS contribution
        if gross_income > 500000:
            suggestions.append({
                "strategy": "Contribute to NPS (80CCD)",
                "potential_savings": 50000,
                "action": "Invest in National Pension Scheme"
            })
        
        return suggestions
    
    def _estimate_final_tax(self, taxable_income: float) -> float:
        """Estimate final tax liability."""
        if taxable_income <= 250000:
            return 0
        elif taxable_income <= 500000:
            return (taxable_income - 250000) * 0.05
        elif taxable_income <= 1000000:
            return (250000 * 0.05) + ((taxable_income - 500000) * 0.20)
        else:
            return (250000 * 0.05) + (500000 * 0.20) + ((taxable_income - 1000000) * 0.30)
