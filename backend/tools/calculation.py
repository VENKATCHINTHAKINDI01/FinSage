"""
Tax Calculation Tools Module
============================

Comprehensive tax calculation tools for agents.
All calculations follow India tax rules (FY 2024-25).
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


# ============================================================================
# TAX SLAB DATA (India FY 2024-25)
# ============================================================================

TAX_SLABS = {
    "individual": [
        {"min": 0, "max": 300000, "rate": 0},
        {"min": 300000, "max": 600000, "rate": 0.05},
        {"min": 600000, "max": 900000, "rate": 0.10},
        {"min": 900000, "max": 1200000, "rate": 0.15},
        {"min": 1200000, "max": float('inf'), "rate": 0.30},
    ],
    "senior_citizen": [
        {"min": 0, "max": 500000, "rate": 0},
        {"min": 500000, "max": 1000000, "rate": 0.05},
        {"min": 1000000, "max": float('inf'), "rate": 0.20},
    ],
    "huf": [
        {"min": 0, "max": 300000, "rate": 0},
        {"min": 300000, "max": 600000, "rate": 0.05},
        {"min": 600000, "max": float('inf'), "rate": 0.30},
    ]
}

SURCHARGE_SLABS = [
    {"min": 0, "max": 5000000, "rate": 0},
    {"min": 5000000, "max": 10000000, "rate": 0.07},
    {"min": 10000000, "max": 20000000, "rate": 0.10},
    {"min": 20000000, "max": 50000000, "rate": 0.15},
    {"min": 50000000, "max": float('inf'), "rate": 0.25},
]

HEALTH_EDUCATION_CESS = 0.04  # 4% on (income tax + surcharge)


# ============================================================================
# DEDUCTION LIMITS (India FY 2024-25)
# ============================================================================

DEDUCTION_LIMITS = {
    "80C": {"limit": 150000, "name": "Life Insurance, ELSS, PPF, NSC", "eligible": ["all"]},
    "80D": {"limit": 150000, "name": "Health Insurance Premium", "eligible": ["all"]},
    "80E": {"limit": None, "name": "Education Loan Interest", "eligible": ["all"]},
    "80TTA": {"limit": 10000, "name": "Savings Account Interest", "eligible": ["individual"]},
    "80TTB": {"limit": 50000, "name": "Senior Citizen Interest", "eligible": ["senior_citizen"]},
    "80CCD": {"limit": 150000, "name": "NPS Contribution", "eligible": ["all"]},
    "80DDB": {"limit": 100000, "name": "Medical Treatment", "eligible": ["all"]},
    "80G": {"limit": None, "name": "Donations", "eligible": ["all"]},
}


# ============================================================================
# TAX CALCULATION ENGINE
# ============================================================================

class TaxCalculationEngine:
    """Core tax calculation engine following India tax rules."""
    
    @staticmethod
    def calculate_income_tax(
        taxable_income: float,
        category: str = "individual",
        age: int = 0,
        has_longterm_capital_gains: bool = False
    ) -> Dict[str, float]:
        """
        Calculate income tax with all components.
        
        Args:
            taxable_income: Taxable income after deductions
            category: 'individual', 'senior_citizen', 'huf'
            age: Age of person (for senior citizen eligibility)
            has_longterm_capital_gains: If income includes LTCG
            
        Returns:
            Dict with tax, surcharge, cess, total
        """
        
        # Determine category based on age if not provided
        if category == "individual" and age >= 60:
            category = "senior_citizen"
        
        # Get applicable tax slabs
        slabs = TAX_SLABS.get(category, TAX_SLABS["individual"])
        
        # Calculate income tax
        income_tax = TaxCalculationEngine._calculate_from_slabs(
            taxable_income,
            slabs
        )
        
        # Calculate surcharge
        surcharge = TaxCalculationEngine._calculate_surcharge(
            income_tax,
            taxable_income
        )
        
        # Calculate cess
        cess = (income_tax + surcharge) * HEALTH_EDUCATION_CESS
        
        # Total tax
        total_tax = income_tax + surcharge + cess
        
        return {
            "income_tax": income_tax,
            "surcharge": surcharge,
            "cess": cess,
            "total_tax": total_tax,
            "effective_rate": (total_tax / taxable_income * 100) if taxable_income > 0 else 0
        }
    
    @staticmethod
    def _calculate_from_slabs(income: float, slabs: list) -> float:
        """Calculate tax using slab method."""
        tax = 0
        
        for slab in slabs:
            if income <= slab["min"]:
                break
            
            taxable_in_slab = min(income, slab["max"]) - slab["min"]
            tax += taxable_in_slab * slab["rate"]
        
        return tax
    
    @staticmethod
    def _calculate_surcharge(income_tax: float, taxable_income: float) -> float:
        """Calculate surcharge based on income."""
        for slab in SURCHARGE_SLABS:
            if slab["min"] <= taxable_income < slab["max"]:
                return income_tax * slab["rate"]
        return 0
    
    @staticmethod
    def calculate_tax_with_deductions(
        gross_income: float,
        deductions: Dict[str, float],
        category: str = "individual",
        age: int = 0
    ) -> Dict[str, Any]:
        """
        Calculate tax after applying deductions.
        
        Args:
            gross_income: Total income before deductions
            deductions: Dict of deduction_code -> amount
            category: Tax category
            age: Age of person
            
        Returns:
            Complete tax calculation breakdown
        """
        
        # Validate and apply deductions
        valid_deductions = {}
        excess_deductions = {}
        
        for deduction_code, amount in deductions.items():
            limits = DEDUCTION_LIMITS.get(deduction_code.upper())
            
            if not limits:
                excess_deductions[deduction_code] = amount
                continue
            
            # Check limit
            limit = limits["limit"]
            if limit and amount > limit:
                valid_deductions[deduction_code] = limit
                excess_deductions[deduction_code] = amount - limit
            else:
                valid_deductions[deduction_code] = amount
        
        # Calculate total deductions
        total_deductions = sum(valid_deductions.values())
        
        # Calculate taxable income
        taxable_income = max(0, gross_income - total_deductions)
        
        # Calculate tax
        tax_breakdown = TaxCalculationEngine.calculate_income_tax(
            taxable_income,
            category,
            age
        )
        
        return {
            "gross_income": gross_income,
            "valid_deductions": valid_deductions,
            "excess_deductions": excess_deductions,
            "total_valid_deductions": total_deductions,
            "taxable_income": taxable_income,
            "income_tax": tax_breakdown["income_tax"],
            "surcharge": tax_breakdown["surcharge"],
            "cess": tax_breakdown["cess"],
            "total_tax": tax_breakdown["total_tax"],
            "effective_tax_rate": tax_breakdown["effective_rate"],
            "deduction_savings": total_deductions * TaxCalculationEngine._estimate_tax_rate(taxable_income)
        }
    
    @staticmethod
    def _estimate_tax_rate(taxable_income: float) -> float:
        """Estimate marginal tax rate for given income."""
        for slab in TAX_SLABS["individual"]:
            if slab["min"] <= taxable_income < slab["max"]:
                return slab["rate"]
        return 0.30
    
    @staticmethod
    def calculate_deduction_benefit(
        deduction_amount: float,
        current_taxable_income: float,
        category: str = "individual"
    ) -> Dict[str, Any]:
        """Calculate tax benefit of adding a deduction."""
        
        # Current tax
        current_tax = TaxCalculationEngine.calculate_income_tax(
            current_taxable_income,
            category
        )
        
        # Tax after deduction
        new_taxable_income = max(0, current_taxable_income - deduction_amount)
        new_tax = TaxCalculationEngine.calculate_income_tax(
            new_taxable_income,
            category
        )
        
        # Calculate savings
        tax_savings = current_tax["total_tax"] - new_tax["total_tax"]
        
        return {
            "deduction_amount": deduction_amount,
            "current_tax": current_tax["total_tax"],
            "tax_after_deduction": new_tax["total_tax"],
            "tax_savings": tax_savings,
            "savings_percentage": (tax_savings / current_tax["total_tax"] * 100) if current_tax["total_tax"] > 0 else 0,
            "effective_deduction_value": deduction_amount * (tax_savings / deduction_amount) if deduction_amount > 0 else 0
        }
    
    @staticmethod
    def calculate_refund(
        tds_paid: float,
        estimated_tax_liability: float,
        other_taxes: float = 0
    ) -> Dict[str, Any]:
        """
        Calculate estimated refund or balance due.
        
        Args:
            tds_paid: Total TDS paid during year
            estimated_tax_liability: Total tax liability
            other_taxes: Other taxes paid (self-assessment, advance tax)
            
        Returns:
            Refund/balance calculation
        """
        
        total_paid = tds_paid + other_taxes
        refund = total_paid - estimated_tax_liability
        
        return {
            "tds_paid": tds_paid,
            "other_taxes_paid": other_taxes,
            "total_paid": total_paid,
            "estimated_tax_liability": estimated_tax_liability,
            "refund_amount": max(0, refund),
            "balance_due": max(0, -refund),
            "refund_expected": refund > 0,
            "interest_on_refund": max(0, refund) * 0.01 if refund > 0 else 0  # 1% per annum simplified
        }


# ============================================================================
# TAX SLABS FOR DIFFERENT INCOME TYPES
# ============================================================================

class CapitalGainsTaxCalculator:
    """Calculate tax on capital gains (short-term vs long-term)."""
    
    @staticmethod
    def calculate_stcg_tax(
        short_term_gains: float,
        total_income: float,
        category: str = "individual"
    ) -> Dict[str, float]:
        """
        Short-term capital gains (STCG) taxed as ordinary income.
        
        Args:
            short_term_gains: STCG amount
            total_income: Total income
            category: Tax category
            
        Returns:
            STCG tax calculation
        """
        
        # STCG added to total income and taxed at slab rates
        total_with_stcg = total_income + short_term_gains
        
        tax_without_stcg = TaxCalculationEngine.calculate_income_tax(
            total_income,
            category
        )["total_tax"]
        
        tax_with_stcg = TaxCalculationEngine.calculate_income_tax(
            total_with_stcg,
            category
        )["total_tax"]
        
        stcg_tax = tax_with_stcg - tax_without_stcg
        
        return {
            "short_term_capital_gains": short_term_gains,
            "tax_on_stcg": stcg_tax,
            "effective_stcg_rate": (stcg_tax / short_term_gains * 100) if short_term_gains > 0 else 0
        }
    
    @staticmethod
    def calculate_ltcg_tax(
        long_term_gains: float,
        category: str = "individual"
    ) -> Dict[str, float]:
        """
        Long-term capital gains (LTCG) taxed at flat rate.
        
        Current rates:
        - Equity LTCG: 20% (with indexation benefit)
        - Non-equity LTCG: 20% (with indexation benefit)
        
        Args:
            long_term_gains: LTCG amount
            category: Tax category
            
        Returns:
            LTCG tax calculation
        """
        
        # Flat 20% on LTCG (simplified, ignoring indexation)
        ltcg_rate = 0.20
        cess = 0.04
        
        ltcg_tax = long_term_gains * ltcg_rate
        ltcg_cess = ltcg_tax * cess
        
        total_ltcg_tax = ltcg_tax + ltcg_cess
        
        return {
            "long_term_capital_gains": long_term_gains,
            "ltcg_tax_rate": ltcg_rate,
            "ltcg_tax": ltcg_tax,
            "cess": ltcg_cess,
            "total_ltcg_tax": total_ltcg_tax,
            "effective_rate": (total_ltcg_tax / long_term_gains * 100) if long_term_gains > 0 else 0
        }


# ============================================================================
# SELF-EMPLOYED / BUSINESS INCOME TAX
# ============================================================================

class BusinessIncomeTaxCalculator:
    """Calculate tax on self-employed/business income."""
    
    @staticmethod
    def calculate_business_tax(
        gross_business_income: float,
        business_expenses: float,
        depreciation: float = 0,
        category: str = "individual",
        age: int = 0
    ) -> Dict[str, Any]:
        """
        Calculate tax on business income.
        
        Args:
            gross_business_income: Total revenue
            business_expenses: Allowable expenses
            depreciation: Depreciation on assets
            category: Tax category
            age: Age for senior citizen exemption
            
        Returns:
            Business income tax calculation
        """
        
        # Calculate profit
        business_profit = gross_business_income - business_expenses - depreciation
        
        # Calculate tax
        tax_breakdown = TaxCalculationEngine.calculate_income_tax(
            max(0, business_profit),
            category,
            age
        )
        
        return {
            "gross_business_income": gross_business_income,
            "business_expenses": business_expenses,
            "depreciation": depreciation,
            "business_profit": business_profit,
            "income_tax": tax_breakdown["income_tax"],
            "surcharge": tax_breakdown["surcharge"],
            "cess": tax_breakdown["cess"],
            "total_tax": tax_breakdown["total_tax"],
            "profit_margin": (business_profit / gross_business_income * 100) if gross_business_income > 0 else 0,
            "effective_tax_rate": tax_breakdown["effective_rate"]
        }


# ============================================================================
# TAX SUMMARY CALCULATOR
# ============================================================================

class ComprehensiveTaxCalculator:
    """Calculate comprehensive tax for multiple income sources."""
    
    @staticmethod
    def calculate_total_tax(
        salary_income: float = 0,
        business_income: float = 0,
        rental_income: float = 0,
        capital_gains: Dict[str, float] = None,
        other_income: float = 0,
        deductions: Dict[str, float] = None,
        tds_paid: float = 0,
        category: str = "individual",
        age: int = 0
    ) -> Dict[str, Any]:
        """
        Calculate tax from all income sources.
        
        Returns comprehensive tax summary.
        """
        
        if capital_gains is None:
            capital_gains = {}
        if deductions is None:
            deductions = {}
        
        # Calculate gross income
        gross_income = salary_income + business_income + rental_income + other_income
        
        # Add capital gains (LTCG taxed separately)
        ltcg = capital_gains.get("long_term", 0)
        stcg = capital_gains.get("short_term", 0)
        
        # For simplicity, add STCG to gross income, track LTCG separately
        gross_income_for_slabs = gross_income + stcg
        
        # Apply deductions
        total_deductions = sum(deductions.values())
        taxable_income = max(0, gross_income_for_slabs - total_deductions)
        
        # Calculate tax on regular income
        regular_income_tax = TaxCalculationEngine.calculate_income_tax(
            taxable_income,
            category,
            age
        )
        
        # Calculate LTCG tax separately
        ltcg_tax_breakdown = CapitalGainsTaxCalculator.calculate_ltcg_tax(ltcg) if ltcg > 0 else {}
        
        # Total tax
        total_tax = regular_income_tax["total_tax"] + ltcg_tax_breakdown.get("total_ltcg_tax", 0)
        
        # Calculate refund
        refund = tds_paid - total_tax
        
        return {
            "income_sources": {
                "salary": salary_income,
                "business": business_income,
                "rental": rental_income,
                "capital_gains": {
                    "short_term": stcg,
                    "long_term": ltcg
                },
                "other": other_income
            },
            "gross_income": gross_income + stcg + ltcg,
            "deductions": deductions,
            "total_deductions": total_deductions,
            "taxable_income": taxable_income,
            "regular_income_tax": regular_income_tax,
            "capital_gains_tax": ltcg_tax_breakdown,
            "total_tax_liability": total_tax,
            "tds_paid": tds_paid,
            "refund": max(0, refund),
            "balance_due": max(0, -refund),
            "effective_tax_rate": (total_tax / (gross_income + stcg + ltcg) * 100) if (gross_income + stcg + ltcg) > 0 else 0
        }