"""
Calculator Tools Module
=======================

Detailed mathematical and tax rule calculators.
Includes HRA exemption and Professional Tax slabs.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class TaxDeductionCalculator:
    """Calculators for specific tax exemptions and professional taxes."""
    
    @staticmethod
    def calculate_hra_exemption(
        basic_salary: float,
        hra_received: float,
        rent_paid: float,
        is_metro: bool = False
    ) -> Dict[str, Any]:
        """
        Calculate HRA (House Rent Allowance) exemption under Section 10(13A).
        
        Exemption is the minimum of:
        1. Actual HRA received.
        2. Rent paid minus 10% of basic salary.
        3. 50% of basic salary (for metro cities) or 40% (for non-metro cities).
        """
        try:
            # Basic salary cannot be negative
            basic_salary = max(0.0, basic_salary)
            hra_received = max(0.0, hra_received)
            rent_paid = max(0.0, rent_paid)
            
            # 10% of basic salary
            ten_percent_basic = basic_salary * 0.10
            
            # Rent paid over 10% of basic
            rent_excess = max(0.0, rent_paid - ten_percent_basic)
            
            # Percentage of basic (50% for metro, 40% for non-metro)
            basic_percentage_limit = basic_salary * (0.50 if is_metro else 0.40)
            
            # Minimum of the three is exempted
            exempt_hra = min(hra_received, rent_excess, basic_percentage_limit)
            taxable_hra = max(0.0, hra_received - exempt_hra)
            
            return {
                "success": True,
                "basic_salary": basic_salary,
                "hra_received": hra_received,
                "rent_paid": rent_paid,
                "is_metro": is_metro,
                "limit_hra_received": hra_received,
                "limit_excess_rent": rent_excess,
                "limit_salary_percentage": basic_percentage_limit,
                "exempt_hra": exempt_hra,
                "taxable_hra": taxable_hra
            }
        except Exception as e:
            logger.error(f"Error calculating HRA exemption: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def calculate_professional_tax(
        state: str,
        monthly_income: float
    ) -> Dict[str, Any]:
        """
        Calculate Professional Tax based on state tax slabs (simplified mock).
        Common states: Maharashtra, Karnataka, Tamil Nadu, West Bengal.
        """
        try:
            state_lower = state.lower().strip()
            pt_amount = 0.0
            
            if "maharashtra" in state_lower:
                if monthly_income > 10000:
                    pt_amount = 200.0  # 2500 per year, roughly 200/month (250 in Feb)
                elif monthly_income > 7500:
                    pt_amount = 175.0
            elif "karnataka" in state_lower:
                if monthly_income > 25000:
                    pt_amount = 200.0
            elif "tamil" in state_lower:
                if monthly_income > 15000:
                    pt_amount = 208.33
                elif monthly_income > 12000:
                    pt_amount = 150.0
            else:
                # Default general PT slab
                if monthly_income > 15000:
                    pt_amount = 200.0
                    
            return {
                "success": True,
                "state": state,
                "monthly_income": monthly_income,
                "monthly_professional_tax": pt_amount,
                "annual_professional_tax": pt_amount * 12
            }
        except Exception as e:
            logger.error(f"Error calculating professional tax: {e}")
            return {"success": False, "error": str(e)}
