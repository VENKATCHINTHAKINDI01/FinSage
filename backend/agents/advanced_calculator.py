"""
Step 9.3: Advanced Calculator Agent
===================================

Complex tax calculations with multiple income sources.
India-specific tax rules + database persistence.
"""

import time
import logging
from typing import Dict, Any, List
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
try:
    from backend.db.orm_models_step9_10 import TaxCalculation
except ImportError:
    from backend.db.orm_models import TaxCalculation
from backend.services.india_tax_data_fetcher import india_tax_data
from backend.agents.base_agent import TaxAgent, AgentOutput

logger = logging.getLogger(__name__)


class AdvancedCalculatorAgent(TaxAgent):
    """
    Handle complex tax calculations.
    
    • Multiple income sources
    • Capital gains (STCG/LTCG)
    • Loss carry forward & set-off
    • GST impact calculation
    • Advance tax computation
    • Tax optimization
    • Save to database
    """
    
    def __init__(self, db: Session = None):
        super().__init__("advanced_calculator_agent", "tax_calculation")
        self.db = db
    
    def set_db(self, db: Session):
        """Set database session."""
        self.db = db
        return self
    
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
          2. Calculate each income type tax
          3. Apply capital gains rules
          4. Apply loss set-off rules
          5. Calculate deductions
          6. Compute final tax liability
          7. Suggest optimizations
          8. Save to database
        """
        start_time = time.time()
        
        if tools is not None:
            self.set_tools(tools)
            
        try:
            self.logger.info(f"Running advanced calculation for user {user_context.get('user_id')}")
            
            user_id = user_context.get("user_id")
            
            # Get India tax data
            tax_data = await india_tax_data.get_current_tax_data()
            
            # STEP 1: Gather income data
            if self.tools:
                income_data = await self.call_tool(
                    "get_user_income_history",
                    user_id=user_id,
                    years=1
                )
                incomes = income_data.get("result", {}).get("income_history", [{}])[0] if income_data.get("result") else {}
            else:
                incomes = user_context
            
            # Extract income sources
            salary = float(incomes.get("salary_income", user_context.get("annual_income", 0) or 0))
            business = float(incomes.get("business_income", 0))
            rental = float(incomes.get("rental_income", 0))
            ltcg = float(user_context.get("long_term_gains", 0) or incomes.get("long_term_gains", 0) or 0)
            stcg = float(user_context.get("short_term_gains", 0) or incomes.get("short_term_gains", 0) or 0)
            other_income = float(incomes.get("other_income", 0))
            
            # STEP 2: Calculate tax on each income type
            tax_components = self._calculate_tax_components(
                salary, business, rental, ltcg, stcg, other_income,
                user_context, tax_data
            )
            
            # STEP 3: Calculate gross income
            gross_income = salary + business + rental + ltcg + stcg + other_income
            
            # STEP 4: Get deductions
            if self.tools:
                deductions_data = await self.call_tool(
                    "get_user_deductions",
                    user_id=user_id
                )
                deductions_dict = deductions_data.get("result", {}).get("deductions", {})
            else:
                deductions_dict = user_context.get("deductions", {})
            
            total_deductions = self._calculate_total_deductions(deductions_dict)
            
            # STEP 5: Apply loss set-off rules
            losses = user_context.get("losses", {})
            loss_setoff = self._apply_loss_setoff(losses, tax_components)
            
            # STEP 6: Calculate taxable income
            taxable_income = max(0, gross_income - total_deductions)
            
            # STEP 7: Calculate final tax liability
            final_tax = self._calculate_final_tax(
                taxable_income,
                user_context,
                tax_data
            )
            
            # STEP 8: Calculate tax components breakdown
            surcharge = self._calculate_surcharge(final_tax, gross_income, tax_data)
            cess = self._calculate_cess(final_tax, surcharge)
            
            total_tax_liability = final_tax + surcharge + cess
            
            # STEP 9: Calculate GST impact (if applicable)
            gst_impact = self._calculate_gst_impact(user_context, business)
            
            # STEP 10: Calculate effective tax rate
            effective_rate = (total_tax_liability / gross_income * 100) if gross_income > 0 else 0
            
            # STEP 11: Optimization suggestions
            optimization = self._suggest_optimizations(
                gross_income,
                total_deductions,
                total_tax_liability,
                user_context,
                tax_data
            )
            
            # STEP 12: Calculate TDS & refund/balance
            tds_paid = float(user_context.get("tds_paid", 0))
            refund = max(0, tds_paid - total_tax_liability)
            balance_due = max(0, total_tax_liability - tds_paid)
            
            result = {
                "financial_year": tax_data["financial_year"],
                "assessment_year": tax_data["assessment_year"],
                
                "gross_income": gross_income,
                "income_breakdown": {
                    "salary": salary,
                    "business": business,
                    "rental": rental,
                    "capital_gains_stcg": stcg,
                    "capital_gains_ltcg": ltcg,
                    "other_income": other_income
                },
                
                "deductions": {
                    "total_claimed": total_deductions,
                    "claimed": total_deductions,  # For backward compatibility with existing tests
                    "details": self._format_deductions(deductions_dict)
                },
                
                "taxable_income": taxable_income,
                
                "tax_calculation": {
                    "salary_tax": tax_components.get("salary_tax", 0),
                    "business_tax": tax_components.get("business_tax", 0),
                    "rental_tax": tax_components.get("rental_tax", 0),
                    "ltcg_tax": tax_components.get("ltcg_tax", 0),
                    "stcg_tax": tax_components.get("stcg_tax", 0),
                    "income_tax": final_tax,
                    "surcharge": surcharge,
                    "cess": cess,
                    "total_tax_liability": total_tax_liability
                },
                
                "tax_breakdown": {  # For backward compatibility with existing tests
                    "income_tax": final_tax,
                    "surcharge": surcharge,
                    "cess": cess
                },
                "total_tax_liability": total_tax_liability,  # For backward compatibility with existing tests
                
                "tax_rates": {
                    "income_tax_rate": self._get_applicable_rate(taxable_income, user_context, tax_data),
                    "surcharge_rate": self._get_surcharge_rate(gross_income, tax_data),
                    "cess_rate": f"{tax_data['cess_rate'] * 100:.0f}%"
                },
                
                "effective_tax_rate": round(effective_rate, 2),
                
                "loss_setoff": loss_setoff,
                "loss_setoff_details": loss_setoff,  # For backward compatibility with existing tests
                
                "gst_details": gst_impact,
                
                "tds_credit": {
                    "tds_paid": tds_paid,
                    "advance_tax_paid": float(user_context.get("advance_tax_paid", 0)),
                    "total_credit": tds_paid + float(user_context.get("advance_tax_paid", 0))
                },
                
                "refund_or_balance": {
                    "estimated_refund": refund,
                    "balance_due": balance_due,
                    "status": f"REFUND ₹{refund:,.0f}" if refund > 0 else (f"PAY ₹{balance_due:,.0f}" if balance_due > 0 else "NO REFUND/TAX"),
                    "notes": [
                        "Refund will be credited within 2-4 weeks",
                        "Balance to be paid before ITR filing deadline",
                        "Amount is estimated, actual may vary"
                    ]
                },
                
                "optimization_suggestions": optimization,
                "potential_savings": sum(s.get("savings", 0) for s in optimization),
                
                "summary": {
                    "total_income": await india_tax_data.format_currency(gross_income),
                    "total_deductions": await india_tax_data.format_currency(total_deductions),
                    "taxable_income": await india_tax_data.format_currency(taxable_income),
                    "total_tax": await india_tax_data.format_currency(total_tax_liability),
                    "effective_rate": f"{effective_rate:.2f}%"
                }
            }
            
            # STEP 13: Save to database
            db_session = self.db
            if not db_session:
                try:
                    from backend.orchestrator.graph import db_session_var
                    db_session = db_session_var.get()
                except Exception:
                    db_session = None
            
            if db_session and user_id:
                await self._save_to_database(user_id, result, db_session)
            
            execution_time = (time.time() - start_time) * 1000
            
            return self._create_output(
                result=result,
                status="success",
                confidence=0.95,
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
    
    def _calculate_tax_components(
        self,
        salary: float,
        business: float,
        rental: float,
        ltcg: float,
        stcg: float,
        other_income: float,
        user_context: Dict[str, Any],
        tax_data: Dict[str, Any]
    ) -> Dict[str, float]:
        """Calculate tax on each income component."""
        
        # Get applicable tax brackets
        is_senior = user_context.get("age", 0) >= 60
        brackets = tax_data["senior_citizen_brackets"] if is_senior else tax_data["tax_brackets"]
        
        components = {}
        
        # Salary tax (taxed as per slab)
        components["salary_tax"] = self._apply_tax_slab(salary, brackets)
        
        # Business income (taxed as per slab)
        components["business_tax"] = self._apply_tax_slab(business, brackets)
        
        # Rental income (taxed as per slab, but can claim deductions)
        rental_after_deductions = max(0, rental * 0.8)  # Assume 20% standard deductions
        components["rental_tax"] = self._apply_tax_slab(rental_after_deductions, brackets)
        
        # Long-term capital gains (20% flat + 4% cess)
        components["ltcg_tax"] = ltcg * 0.20 * 1.04
        
        # Short-term capital gains (taxed as per slab)
        components["stcg_tax"] = self._apply_tax_slab(stcg, brackets)
        
        # Other income (taxed as per slab)
        components["other_tax"] = self._apply_tax_slab(other_income, brackets)
        
        return components
    
    def _apply_tax_slab(self, income: float, brackets: List[Dict]) -> float:
        """Apply tax slab rates to income."""
        if income <= 0:
            return 0
        
        tax = 0
        for bracket in brackets:
            if income > bracket["min"]:
                taxable_in_bracket = min(income, bracket["max"]) - bracket["min"]
                tax += taxable_in_bracket * bracket["rate"]
        
        return tax
    
    def _calculate_total_deductions(self, deductions_dict: Dict[str, Any]) -> float:
        """Calculate total deductions from dict."""
        if not deductions_dict:
            return 0
        
        total = 0
        if isinstance(deductions_dict, dict):
            for deduction in deductions_dict.values():
                if isinstance(deduction, dict):
                    total += deduction.get("amount", deduction.get("claimed", 0))
                else:
                    total += float(deduction)
        
        return min(total, 1500000)  # Cap at standard limit
    
    def _apply_loss_setoff(
        self,
        losses: Dict[str, float],
        tax_components: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Apply loss set-off rules (India-specific).
        
        Rules:
        • Business loss can offset any income
        • Capital loss can only offset capital gains
        """
        business_loss = losses.get("business", 0)
        capital_loss = losses.get("capital", 0)
        
        # Capital loss set-off (only against capital gains)
        capital_gains = tax_components.get("ltcg_tax", 0) + tax_components.get("stcg_tax", 0)
        capital_loss_utilized = min(capital_loss, capital_gains)
        capital_loss_carried = max(0, capital_loss - capital_gains)
        
        # Business loss set-off
        other_income = tax_components.get("salary_tax", 0) + tax_components.get("rental_tax", 0)
        business_loss_utilized = min(business_loss, other_income)
        business_loss_carried = max(0, business_loss - other_income)
        
        return {
            "business_loss_used": business_loss_utilized,
            "business_loss_carried_forward": business_loss_carried,
            "capital_loss_used": capital_loss_utilized,
            "capital_loss_carried_forward": capital_loss_carried,
            "carryforward_limit": "Business: 8 years | Capital: Indefinite",
            "note": "Can carry forward unused losses to next year"
        }
    
    def _calculate_final_tax(
        self,
        taxable_income: float,
        user_context: Dict[str, Any],
        tax_data: Dict[str, Any]
    ) -> float:
        """Calculate final income tax on taxable income."""
        is_senior = user_context.get("age", 0) >= 60
        brackets = tax_data["senior_citizen_brackets"] if is_senior else tax_data["tax_brackets"]
        
        return self._apply_tax_slab(taxable_income, brackets)
    
    def _calculate_surcharge(
        self,
        income_tax: float,
        gross_income: float,
        tax_data: Dict[str, Any]
    ) -> float:
        """Calculate surcharge on income tax (India-specific)."""
        surcharge_slabs = tax_data["surcharge_slabs"]
        
        surcharge = 0
        for slab in surcharge_slabs:
            if gross_income > slab["min"]:
                surcharge = income_tax * slab["rate"]
                break
        
        return surcharge
    
    def _calculate_cess(self, income_tax: float, surcharge: float) -> float:
        """Calculate 4% health & education cess."""
        return (income_tax + surcharge) * 0.04
    
    def _calculate_gst_impact(
        self,
        user_context: Dict[str, Any],
        business_income: float
    ) -> Dict[str, Any]:
        """Calculate GST impact if applicable."""
        gst_data = {}
        
        turnover = business_income + user_context.get("turnover", 0)
        
        if turnover > 4000000:  # ₹40 lakh threshold
            gst_data = {
                "gst_applicable": True,
                "threshold": 4000000,
                "turnover": turnover,
                "registration_required": True,
                "gst_to_pay": turnover * 0.18,  # Assume 18% GST
                "gst_refund_potential": turnover * 0.18 * 0.3,  # Estimated ITC
                "net_gst_liability": turnover * 0.18 * 0.7,
                "filing_requirement": "Monthly GSTR-1, Quarterly GSTR-3B",
                "action": "Register on GST portal if not done"
            }
        else:
            gst_data = {
                "gst_applicable": False,
                "threshold": 4000000,
                "turnover": turnover,
                "registration_required": False,
                "message": "Below GST threshold - registration optional"
            }
        
        return gst_data
    
    def _get_applicable_rate(
        self,
        taxable_income: float,
        user_context: Dict[str, Any],
        tax_data: Dict[str, Any]
    ) -> str:
        """Get applicable tax rate."""
        is_senior = user_context.get("age", 0) >= 60
        brackets = tax_data["senior_citizen_brackets"] if is_senior else tax_data["tax_brackets"]
        
        for bracket in brackets:
            if taxable_income >= bracket["min"] and taxable_income < bracket["max"]:
                return f"{bracket['rate'] * 100:.0f}%"
        
        return "30%"  # Default highest rate
    
    def _get_surcharge_rate(self, gross_income: float, tax_data: Dict[str, Any]) -> str:
        """Get applicable surcharge rate."""
        surcharge_slabs = tax_data["surcharge_slabs"]
        
        for slab in surcharge_slabs:
            if gross_income >= slab["min"] and gross_income < slab["max"]:
                return f"{slab['rate'] * 100:.0f}%"
        
        return "25%"  # Highest surcharge
    
    def _format_deductions(self, deductions_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Format deductions for display."""
        deduction_list = []
        
        if isinstance(deductions_dict, dict):
            for code, details in deductions_dict.items():
                if isinstance(details, dict):
                    deduction_list.append({
                        "code": code,
                        "name": details.get("name", code),
                        "amount": details.get("amount", details.get("claimed", 0)),
                        "limit": details.get("limit", "No limit")
                    })
                else:
                    deduction_list.append({
                        "code": code,
                        "name": code,
                        "amount": float(details),
                        "limit": "No limit"
                    })
        
        return deduction_list[:10]  # Top 10
    
    def _suggest_optimizations(
        self,
        gross_income: float,
        current_deductions: float,
        tax_liability: float,
        user_context: Dict[str, Any],
        tax_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Suggest tax optimization strategies (India-specific)."""
        suggestions = []
        deduction_limits = tax_data["deduction_limits"]
        
        # Suggestion 1: Maximize 80C
        deduction_80c_limit = deduction_limits["80C"]["limit"]
        if current_deductions < deduction_80c_limit:
            headroom = deduction_80c_limit - current_deductions
            tax_savings = headroom * 0.20
            suggestions.append({
                "strategy": "Maximize 80C (Life Insurance, ELSS, PPF, NSC)",
                "headroom": headroom,
                "potential_savings": tax_savings,
                "savings": tax_savings,
                "difficulty": "Easy",
                "action": f"Invest additional ₹{headroom:,.0f} before March 31"
            })
        
        # Suggestion 2: Health Insurance (80D)
        if not user_context.get("has_health_insurance") and not user_context.get("health_insurance"):
            suggestions.append({
                "strategy": "Get health insurance (80D deduction)",
                "potential_savings": 30000,
                "savings": 30000,
                "difficulty": "Easy",
                "action": "Buy health insurance policy (₹150,000 max limit)"
            })
        
        # Suggestion 3: NPS Contribution (80CCD)
        if gross_income > 500000:
            suggestions.append({
                "strategy": "Contribute to NPS (Additional 80CCD)",
                "potential_savings": 50000,
                "savings": 50000,
                "difficulty": "Medium",
                "action": "Open NPS account and invest ₹150,000"
            })
        
        # Suggestion 4: Education Loan (80E)
        if user_context.get("education_loan", 0) > 0:
            suggestions.append({
                "strategy": "Claim education loan interest (80E)",
                "potential_savings": user_context.get("education_loan", 0) * 0.20,
                "savings": user_context.get("education_loan", 0) * 0.20,
                "difficulty": "Easy",
                "action": "Claim interest paid on education loan"
            })
        
        # Suggestion 5: Loss Carry Forward
        losses = user_context.get("losses", {})
        if losses.get("capital", 0) > 0 or losses.get("business", 0) > 0:
            suggestions.append({
                "strategy": "Use loss carry forward wisely",
                "potential_savings": sum(losses.values()) * 0.20,
                "savings": sum(losses.values()) * 0.20,
                "difficulty": "Hard",
                "action": "Consult CA for optimal loss set-off strategy"
            })
        
        return suggestions
    
    async def _save_to_database(self, user_id: str, result: Dict[str, Any], db_session):
        """Save tax calculation to database."""
        try:
            tax_calc = TaxCalculation(
                user_id=user_id,
                financial_year=result["financial_year"],
                income_sources=result["income_breakdown"],
                deductions=result.get("deductions"),
                capital_gains={"stcg": result["income_breakdown"]["capital_gains_stcg"], 
                              "ltcg": result["income_breakdown"]["capital_gains_ltcg"]},
                losses=None,
                gross_income=Decimal(str(result["gross_income"])),
                taxable_income=Decimal(str(result["taxable_income"])),
                income_tax=Decimal(str(result["tax_calculation"]["income_tax"])),
                surcharge=Decimal(str(result["tax_calculation"]["surcharge"])),
                cess=Decimal(str(result["tax_calculation"]["cess"])),
                total_tax_liability=Decimal(str(result["tax_calculation"]["total_tax_liability"])),
                effective_rate=Decimal(str(result["effective_tax_rate"])),
                optimization_suggestions=result.get("optimization_suggestions")
            )
            
            db_session.add(tax_calc)
            
            if isinstance(db_session, AsyncSession):
                await db_session.commit()
            else:
                db_session.commit()
            self.logger.info(f"Tax calculation saved for user {user_id}")
        
        except Exception as e:
            self.logger.error(f"Error saving to database: {e}")
            try:
                if isinstance(db_session, AsyncSession):
                    await db_session.rollback()
                else:
                    db_session.rollback()
            except Exception as rollback_err:
                self.logger.error(f"Error rolling back: {rollback_err}")
