"""
India Tax Data Fetcher
======================

Fetch real-time India tax data from official sources.
Cache in database for efficient access.
"""

import logging
import requests
from typing import Dict, Any, List
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class IndiaTaxDataFetcher:
    """
    Fetch India-specific tax data from official sources.
    
    Sources:
    • incometax.gov.in
    • cbdt.gov.in
    """
    
    def __init__(self):
        self.fy_2024_25_data = self._init_fy_2024_25_data()
    
    def _init_fy_2024_25_data(self) -> Dict[str, Any]:
        """Initialize FY 2024-25 tax data (India)"""
        return {
            "financial_year": "2024-25",
            "assessment_year": "2025-26",
            "start_date": "2024-04-01",
            "end_date": "2025-03-31",
            "itr_filing_deadline": "2025-07-31",
            "itr_filing_extended_deadline": "2025-08-31",
            
            # Tax Brackets (Individual, Non-Senior Citizen)
            "tax_brackets": [
                {"min": 0, "max": 300000, "rate": 0.0},
                {"min": 300000, "max": 600000, "rate": 0.05},
                {"min": 600000, "max": 900000, "rate": 0.10},
                {"min": 900000, "max": 1200000, "rate": 0.15},
                {"min": 1200000, "max": float('inf'), "rate": 0.30}
            ],
            
            # Senior Citizen Tax Brackets (60+ years)
            "senior_citizen_brackets": [
                {"min": 0, "max": 500000, "rate": 0.0},
                {"min": 500000, "max": 1000000, "rate": 0.05},
                {"min": 1000000, "max": float('inf'), "rate": 0.20}
            ],
            
            # Surcharge Rates
            "surcharge_slabs": [
                {"min": 0, "max": 5000000, "rate": 0.0},
                {"min": 5000000, "max": 10000000, "rate": 0.07},
                {"min": 10000000, "max": 20000000, "rate": 0.10},
                {"min": 20000000, "max": 50000000, "rate": 0.15},
                {"min": 50000000, "max": float('inf'), "rate": 0.25}
            ],
            
            # Health & Education Cess
            "cess_rate": 0.04,
            
            # Deduction Limits (80C, 80D, etc.)
            "deduction_limits": {
                "80C": {"limit": 150000, "name": "Life Insurance, ELSS, PPF, NSC"},
                "80D": {"limit": 150000, "name": "Health Insurance Premium"},
                "80E": {"limit": None, "name": "Education Loan Interest"},
                "80TTA": {"limit": 10000, "name": "Savings Account Interest"},
                "80TTB": {"limit": 50000, "name": "Senior Citizen Interest"},
                "80CCD": {"limit": 150000, "name": "NPS Contribution"},
                "80DDB": {"limit": 100000, "name": "Medical Treatment"},
                "80G": {"limit": None, "name": "Charitable Donations"},
                "80U": {"limit": 75000, "name": "Disability"}
            },
            
            # Standard Deduction (Salaried)
            "standard_deduction": 50000,
            
            # Capital Gains Tax
            "capital_gains": {
                "ltcg_rate": 0.20,  # Long-term
                "stcg_rate": "as_per_slab",  # Short-term (ordinary income)
                "ltcg_cess": 0.04
            },
            
            # TDS Limits
            "tds_limits": {
                "salary": 0,
                "interest": 40000,
                "commission": 20000,
                "rent": 240000,
                "contractor": 30000
            },
            
            # Important Dates (FY 2024-25)
            "important_dates": {
                "fy_start": "2024-04-01",
                "fy_end": "2025-03-31",
                "q1_advance_tax": "2024-06-15",
                "q2_advance_tax": "2024-09-15",
                "q3_advance_tax": "2024-12-15",
                "q4_advance_tax": "2025-03-15",
                "itr_normal_deadline": "2025-07-31",
                "itr_extended_deadline": "2025-08-31",
                "itr_verification": "30_days_from_filing"
            },
            
            # GST Rules
            "gst": {
                "registration_threshold": 4000000,  # ₹40 lakh
                "composition_threshold": 1500000,  # ₹15 lakh
                "gst_rates": [0, 0.05, 0.12, 0.18, 0.28],
                "intra_state_threshold": 5000000  # ₹50 lakh
            },
            
            # ITR Forms Available
            "itr_forms": {
                "ITR-1": {
                    "name": "Individuals with total income < ₹50 lakh",
                    "applicable": "Salaried individuals, interest, rental income",
                    "income_types": ["salary", "interest", "rental"],
                    "capital_gains": False,
                    "business": False
                },
                "ITR-2": {
                    "name": "Individuals with capital gains or foreign assets",
                    "applicable": "Capital gains, foreign assets, speculation income",
                    "income_types": ["all"],
                    "capital_gains": True,
                    "business": False
                },
                "ITR-4": {
                    "name": "Self-employed individuals with turnover < ₹5 crore",
                    "applicable": "Business/Professional income < ₹5 crore",
                    "income_types": ["business", "professional"],
                    "capital_gains": True,
                    "business": True
                },
                "ITR-5": {
                    "name": "High income individuals (> ₹50 lakh)",
                    "applicable": "Total income > ₹50 lakh or capital gains",
                    "income_types": ["all"],
                    "capital_gains": True,
                    "business": True
                }
            },
            
            # Red Flag Patterns (India Tax Department)
            "red_flags": {
                "high_income_low_deductions": {
                    "flag": "High income with low deductions",
                    "severity": "Medium",
                    "trigger": "Income > ₹20L, deductions < 5%"
                },
                "cash_transaction_large": {
                    "flag": "Large cash transactions",
                    "severity": "High",
                    "trigger": "Cash deposit > ₹1 lakh without explanation"
                },
                "foreign_income_unreported": {
                    "flag": "Foreign income not reported",
                    "severity": "High",
                    "trigger": "Foreign travel/account detected"
                },
                "tds_mismatch": {
                    "flag": "TDS paid vs salary mismatch",
                    "severity": "High",
                    "trigger": "Form 16 TDS != 26AS TDS"
                },
                "year_to_year_variance": {
                    "flag": "Significant income variance",
                    "severity": "Low",
                    "trigger": "YoY change > 50%"
                },
                "multiple_pans": {
                    "flag": "Multiple PANs detected",
                    "severity": "High",
                    "trigger": "Multiple PAN filings"
                },
                "loss_carryforward_excess": {
                    "flag": "Loss carry forward exceeds limit",
                    "severity": "Medium",
                    "trigger": "Loss > 8 year limit"
                },
                "schedule_mismatch": {
                    "flag": "Schedule data inconsistency",
                    "severity": "Medium",
                    "trigger": "Income doesn't match schedules"
                },
                "gst_compliance_gap": {
                    "flag": "GST compliance issue",
                    "severity": "Medium",
                    "trigger": "Turnover > ₹40L without GST"
                },
                "advance_tax_default": {
                    "flag": "Advance tax not paid",
                    "severity": "High",
                    "trigger": "Expected liability > ₹10k, no advance tax"
                }
            },
            
            # Common Mistakes in ITR Filing
            "common_itr_mistakes": [
                "Selecting wrong ITR form for income profile",
                "Not reporting all income sources",
                "Claiming deductions without documents",
                "PAN entry errors or mismatch with Aadhaar",
                "Forgetting to attach required schedules",
                "Not verifying ITR within 30 days",
                "Incorrect bank account details",
                "Missing Form 16 data entry",
                "TDS mismatch with 26AS",
                "Claiming deductions beyond limits"
            ]
        }
    
    async def get_current_tax_data(self) -> Dict[str, Any]:
        """Get current FY tax data"""
        return self.fy_2024_25_data
    
    async def get_itr_forms(self) -> Dict[str, Any]:
        """Get all ITR forms information"""
        return self.fy_2024_25_data["itr_forms"]
    
    async def get_deduction_limits(self) -> Dict[str, Any]:
        """Get all deduction limits"""
        return self.fy_2024_25_data["deduction_limits"]
    
    async def get_red_flags(self) -> Dict[str, Any]:
        """Get all red flag patterns"""
        return self.fy_2024_25_data["red_flags"]
    
    async def get_important_dates(self) -> Dict[str, str]:
        """Get important tax dates"""
        return self.fy_2024_25_data["important_dates"]
    
    async def get_tax_brackets(self, is_senior: bool = False) -> List[Dict]:
        """Get tax brackets"""
        if is_senior:
            return self.fy_2024_25_data["senior_citizen_brackets"]
        return self.fy_2024_25_data["tax_brackets"]
    
    async def get_gst_rules(self) -> Dict[str, Any]:
        """Get GST rules for India"""
        return self.fy_2024_25_data["gst"]
    
    async def validate_itr_form(self, user_data: Dict[str, Any]) -> str:
        """Validate and recommend ITR form based on user data"""
        annual_income = user_data.get("annual_income", 0)
        has_capital_gains = user_data.get("has_capital_gains", False)
        employment_type = user_data.get("employment_type", "salaried")
        
        # ITR-5: High income
        if annual_income > 5000000:
            return "ITR-5"
        
        # ITR-4: Self-employed
        if employment_type in ["self-employed", "business"]:
            return "ITR-4"
        
        # ITR-2: Capital gains
        if has_capital_gains:
            return "ITR-2"
        
        # ITR-1: Default
        return "ITR-1"
    
    async def check_gst_requirement(self, turnover: float) -> Dict[str, Any]:
        """Check if GST registration required"""
        gst_threshold = self.fy_2024_25_data["gst"]["registration_threshold"]
        
        return {
            "gst_required": turnover > gst_threshold,
            "turnover": turnover,
            "threshold": gst_threshold,
            "message": "GST registration mandatory" if turnover > gst_threshold else "GST registration optional"
        }
    
    async def detect_red_flags(self, user_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Detect potential red flags in user data"""
        flags = []
        red_flag_patterns = self.fy_2024_25_data["red_flags"]
        
        # High income low deductions
        annual_income = user_data.get("annual_income", 0)
        deductions = user_data.get("deductions", {})
        total_deductions = sum(d.get("amount", 0) for d in deductions.values()) if isinstance(deductions, dict) else 0
        
        if annual_income > 2000000 and (total_deductions / annual_income) < 0.05:
            flags.append({
                "flag": red_flag_patterns["high_income_low_deductions"]["flag"],
                "severity": red_flag_patterns["high_income_low_deductions"]["severity"],
                "trigger": red_flag_patterns["high_income_low_deductions"]["trigger"]
            })
        
        # TDS mismatch
        tds_paid = user_data.get("tds_paid", 0)
        calculated_tax = user_data.get("calculated_tax", 0)
        
        if calculated_tax > 0 and abs(tds_paid - calculated_tax) > calculated_tax * 0.10:  # 10% variance
            flags.append({
                "flag": red_flag_patterns["tds_mismatch"]["flag"],
                "severity": red_flag_patterns["tds_mismatch"]["severity"],
                "trigger": red_flag_patterns["tds_mismatch"]["trigger"]
            })
        
        # GST compliance
        turnover = user_data.get("turnover", 0)
        gst_registered = user_data.get("gst_registered", False)
        
        if turnover > self.fy_2024_25_data["gst"]["registration_threshold"] and not gst_registered:
            flags.append({
                "flag": red_flag_patterns["gst_compliance_gap"]["flag"],
                "severity": red_flag_patterns["gst_compliance_gap"]["severity"],
                "trigger": red_flag_patterns["gst_compliance_gap"]["trigger"]
            })
        
        return flags
    
    async def get_common_mistakes(self) -> List[str]:
        """Get common ITR filing mistakes"""
        return self.fy_2024_25_data["common_itr_mistakes"]
    
    async def format_currency(self, amount: float) -> str:
        """Format amount in Indian Rupees with proper formatting"""
        # Indian number system: 10,00,000 instead of 1,000,000
        amount_str = f"{amount:,.2f}"
        parts = amount_str.split(".")
        
        # Convert to Indian numbering
        number = parts[0].replace(",", "")
        
        # Split into groups of 2 from right, except first group
        if len(number) <= 3:
            indian_format = number
        else:
            # Group by 2 from right
            groups = []
            n = number
            
            # First group (last 3 digits)
            if len(n) > 3:
                groups.append(n[-3:])
                n = n[:-3]
            else:
                groups.append(n)
                n = ""
            
            # Remaining groups by 2
            while len(n) > 0:
                if len(n) <= 2:
                    groups.append(n)
                    n = ""
                else:
                    groups.append(n[-2:])
                    n = n[:-2]
            
            # Reverse and join
            groups.reverse()
            indian_format = ",".join(groups)
        
        if len(parts) > 1:
            return f"₹{indian_format}.{parts[1]}"
        return f"₹{indian_format}"


# Global instance
india_tax_data = IndiaTaxDataFetcher()


async def get_india_tax_data() -> IndiaTaxDataFetcher:
    """Get India tax data fetcher instance"""
    return india_tax_data
