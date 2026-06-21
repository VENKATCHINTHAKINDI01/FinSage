"""
Web Search and Government Scheme Tools
======================================

Tools for:
- Searching latest tax information
- Looking up government schemes
- Retrieving scheme eligibility details
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


# ============================================================================
# GOVERNMENT SCHEMES DATABASE
# ============================================================================

class GovernmentSchemesDatabase:
    """Comprehensive database of Indian government tax saving schemes."""
    
    SCHEMES = {
        "80C": {
            "name": "Life Insurance, Investments and Savings",
            "section": "Section 80C",
            "limit": 150000,
            "category": "deduction",
            "applicable_to": ["individual", "huf"],
            "description": "Deduction on investments in ELSS, PPF, Life Insurance, NSC, FDs (5+ years), etc.",
            "eligible_investments": [
                "ELSS (Equity Linked Savings Scheme)",
                "Public Provident Fund (PPF)",
                "Life Insurance Premium",
                "National Savings Certificate (NSC)",
                "Fixed Deposits (5+ years)",
                "Sukanya Samriddhi Scheme (for girl child)",
                "Senior Citizens Saving Scheme",
                "Post Office Savings Account"
            ],
            "lock_in_period": "3 years (ELSS), 15 years (PPF), till maturity",
            "benefits": "Direct tax deduction up to ₹150,000",
            "documents_needed": ["Investment receipts", "Certificates"],
            "effectiveness": "High - direct reduction in taxable income",
            "risk": "Low"
        },
        
        "80D": {
            "name": "Health Insurance Premium",
            "section": "Section 80D",
            "limit": 150000,
            "category": "deduction",
            "applicable_to": ["individual", "huf"],
            "description": "Deduction on health insurance premiums for self, spouse, children, and parents.",
            "eligible_policies": [
                "Health Insurance",
                "Critical Illness Insurance",
                "Accident Insurance",
                "Specific Disease Insurance"
            ],
            "who_can_claim": [
                "Self",
                "Spouse",
                "Children (dependent or not)",
                "Parents (dependent or not)"
            ],
            "limits": {
                "self_spouse_children": 75000,
                "parents": 75000,
                "total": 150000
            },
            "benefits": "Tax deduction on insurance premiums",
            "documents_needed": ["Insurance policy", "Premium receipts", "Proof of payment"],
            "effectiveness": "High - direct reduction in taxable income",
            "risk": "Very Low"
        },
        
        "80E": {
            "name": "Education Loan Interest",
            "section": "Section 80E",
            "limit": None,
            "category": "deduction",
            "applicable_to": ["individual"],
            "description": "Deduction on interest paid on loan taken for higher education.",
            "eligibility": "Student or parent of student who took loan for education",
            "qualified_education": [
                "Undergraduate degree",
                "Postgraduate degree",
                "Professional courses (CA, CS, etc.)",
                "Graduate programs",
                "Vocational courses (recognized)"
            ],
            "duration": "8 years from the year interest payment starts",
            "benefits": "Full deduction on interest paid (no limit)",
            "documents_needed": ["Loan agreement", "Interest receipts", "Course enrollment certificate"],
            "effectiveness": "Very High - no limit on deduction",
            "risk": "Very Low"
        },
        
        "80TTA": {
            "name": "Savings Account Interest (Regular Citizens)",
            "section": "Section 80TTA",
            "limit": 10000,
            "category": "deduction",
            "applicable_to": ["individual"],
            "age_restriction": "Must not be senior citizen (< 60 years)",
            "description": "Deduction on interest earned from savings accounts.",
            "eligible_interest": [
                "Savings Account Interest",
                "Interest on Savings Deposits"
            ],
            "benefits": "Tax deduction up to ₹10,000 on savings interest",
            "documents_needed": ["Bank statements", "Interest statements"],
            "effectiveness": "Low to Medium - small deduction",
            "risk": "Very Low"
        },
        
        "80TTB": {
            "name": "Senior Citizen Interest Income",
            "section": "Section 80TTB",
            "limit": 50000,
            "category": "deduction",
            "applicable_to": ["individual"],
            "age_restriction": "Must be 60+ years",
            "description": "Deduction for senior citizens on interest income from deposits.",
            "eligible_interest": [
                "Interest from savings deposits",
                "Interest from fixed deposits",
                "Interest from recurring deposits"
            ],
            "benefits": "Tax deduction up to ₹50,000 on savings interest",
            "documents_needed": ["Bank statements", "Interest certificates"],
            "effectiveness": "Medium",
            "risk": "Very Low"
        },
        
        "80CCD": {
            "name": "National Pension Scheme (NPS)",
            "section": "Section 80CCD",
            "limit": 150000,
            "category": "deduction",
            "applicable_to": ["individual"],
            "description": "Deduction on contributions to National Pension Scheme.",
            "benefits": [
                "Tax deduction on NPS contributions",
                "Monthly pension after retirement",
                "Partial withdrawal allowed"
            ],
            "nps_tiers": {
                "tier1": "Main account (mandatory for pension)",
                "tier2": "Optional savings account"
            },
            "contribution_options": [
                "Regular monthly contributions",
                "Ad-hoc contributions",
                "Employer contributions"
            ],
            "documents_needed": ["NPS transaction receipt", "NPS account statement"],
            "effectiveness": "Very High - deduction + pension",
            "risk": "Low - Government regulated"
        },
        
        "80DDB": {
            "name": "Medical Treatment of Serious Illness",
            "section": "Section 80DDB",
            "limit": 100000,
            "category": "deduction",
            "applicable_to": ["individual"],
            "description": "Deduction for medical treatment/spent on serious illness.",
            "eligible_treatments": [
                "Medical treatment of specified diseases",
                "Diagnosis and treatment",
                "Hospital expenses",
                "Diagnostic tests"
            ],
            "eligible_diseases": [
                "Cancer",
                "Diabetes",
                "Heart disease",
                "Neurological disorders",
                "Organ transplant"
            ],
            "benefits": "Tax deduction up to ₹100,000",
            "documents_needed": ["Medical receipts", "Doctor's prescription", "Hospital bills"],
            "effectiveness": "High - when applicable",
            "risk": "Very Low"
        },
        
        "80G": {
            "name": "Donations to Charitable Institutions",
            "section": "Section 80G",
            "limit": None,
            "category": "deduction",
            "applicable_to": ["individual", "huf"],
            "description": "Deduction on donations to eligible charitable organizations.",
            "eligible_donations": [
                "Donations to national defense fund",
                "Donations to PM relief fund",
                "Donations to registered charities",
                "Donations to religious/educational institutions"
            ],
            "deduction_options": [
                "100% deduction (limited charities)",
                "50% deduction (for most organizations)"
            ],
            "benefits": "Tax deduction on charitable donations",
            "documents_needed": ["Donation receipts", "80G certificate from organization"],
            "effectiveness": "Medium",
            "risk": "Very Low"
        },
        
        "80U": {
            "name": "Disabilities",
            "section": "Section 80U",
            "limit": 75000,
            "category": "deduction",
            "applicable_to": ["individual"],
            "description": "Deduction for persons with disabilities.",
            "eligible_disabilities": [
                "Severe disability (40%+)",
                "Very severe disability (80%+)"
            ],
            "benefits": {
                "severe": 75000,
                "very_severe": 125000
            },
            "documents_needed": ["Medical certificate", "Disability certificate"],
            "effectiveness": "High",
            "risk": "Very Low"
        }
    }
    
    @classmethod
    def get_scheme(cls, scheme_code: str) -> Optional[Dict[str, Any]]:
        """Get details of a specific scheme."""
        return cls.SCHEMES.get(scheme_code.upper())
    
    @classmethod
    def list_all_schemes(cls) -> List[Dict[str, Any]]:
        """List all available schemes."""
        return [
            {
                "code": code,
                "name": details["name"],
                "limit": details.get("limit"),
                "category": details.get("category")
            }
            for code, details in cls.SCHEMES.items()
        ]
    
    @classmethod
    def search_schemes(cls, keyword: str) -> List[Dict[str, Any]]:
        """Search schemes by keyword."""
        results = []
        keyword_lower = keyword.lower()
        
        for code, details in cls.SCHEMES.items():
            if (keyword_lower in details["name"].lower() or
                keyword_lower in details.get("description", "").lower()):
                results.append({
                    "code": code,
                    "name": details["name"],
                    "description": details.get("description")
                })
        
        return results


# ============================================================================
# SCHEME LOOKUP TOOL
# ============================================================================

class SchemeLookupTool:
    """Look up government scheme details."""
    
    def __init__(self):
        self.logger = logging.getLogger("tool.scheme_lookup")
    
    async def get_scheme_details(self, scheme_code: str) -> Dict[str, Any]:
        """
        Get detailed information about a scheme.
        
        Args:
            scheme_code: Scheme code (e.g., "80C")
            
        Returns:
            Detailed scheme information
        """
        try:
            scheme = GovernmentSchemesDatabase.get_scheme(scheme_code)
            
            if not scheme:
                return {
                    "success": False,
                    "message": f"Scheme {scheme_code} not found",
                    "available_schemes": [s["code"] for s in GovernmentSchemesDatabase.list_all_schemes()]
                }
            
            return {
                "success": True,
                "scheme_code": scheme_code,
                "details": scheme
            }
        
        except Exception as e:
            self.logger.error(f"Error getting scheme details: {e}")
            return {"success": False, "error": str(e)}
    
    async def search_schemes_by_keyword(self, keyword: str) -> Dict[str, Any]:
        """Search schemes by keyword."""
        try:
            results = GovernmentSchemesDatabase.search_schemes(keyword)
            
            return {
                "success": True,
                "keyword": keyword,
                "results": results,
                "count": len(results)
            }
        except Exception as e:
            self.logger.error(f"Error searching schemes: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_applicable_schemes(
        self,
        age: int,
        employment_type: str,
        has_health_insurance: bool = False,
        has_education_loan: bool = False
    ) -> Dict[str, Any]:
        """
        Get schemes applicable to user based on profile.
        
        Args:
            age: Age of user
            employment_type: "salaried", "self_employed", "retired"
            has_health_insurance: Whether user has health insurance
            has_education_loan: Whether user has education loan
            
        Returns:
            List of applicable schemes with recommendations
        """
        try:
            applicable = []
            
            for code, scheme in GovernmentSchemesDatabase.SCHEMES.items():
                is_applicable = True
                reason = []
                
                # Age checks
                if "age_restriction" in scheme:
                    if "60+" in scheme["age_restriction"]:
                        if age < 60:
                            is_applicable = False
                            reason.append(f"Requires age 60+")
                    elif "< 60" in scheme["age_restriction"]:
                        if age >= 60:
                            is_applicable = False
                            reason.append(f"For individuals under 60 years")
                
                # Employment type checks
                if employment_type == "salaried" and code == "44ADA":
                    is_applicable = False
                    reason.append("Not applicable to salaried employees")
                
                # Insurance checks
                if code == "80D" and not has_health_insurance:
                    # Can still be applicable if buying insurance
                    reason.append("Requires health insurance policy")
                
                # Education loan checks
                if code == "80E" and not has_education_loan:
                    is_applicable = False
                    reason.append("Requires active education loan")
                
                if is_applicable:
                    applicable.append({
                        "code": code,
                        "name": scheme["name"],
                        "limit": scheme.get("limit"),
                        "description": scheme.get("description"),
                        "recommendation_strength": "High" if not reason else "Medium"
                    })
            
            return {
                "success": True,
                "user_profile": {
                    "age": age,
                    "employment_type": employment_type
                },
                "applicable_schemes": applicable,
                "count": len(applicable)
            }
        except Exception as e:
            self.logger.error(f"Error getting applicable schemes: {e}")
            return {"success": False, "error": str(e)}

    async def check_scheme_eligibility(
        self,
        scheme_code: str,
        user_age: int,
        user_income: float,
        has_health_insurance: bool = False,
        has_education_loan: bool = False
    ) -> Dict[str, Any]:
        """
        Check if user is eligible for a specific scheme.
        """
        try:
            scheme = GovernmentSchemesDatabase.get_scheme(scheme_code)
            if not scheme:
                return {
                    "success": False,
                    "error": f"Scheme {scheme_code} not found",
                    "eligible": False,
                    "reasons": [f"Scheme {scheme_code} is not recognized in database"]
                }
            
            eligible = True
            reasons = []
            
            # Age restriction check
            if "age_restriction" in scheme:
                age_rest = scheme["age_restriction"]
                if "60+" in age_rest and user_age < 60:
                    eligible = False
                    reasons.append(f"Requires age 60+ (User age: {user_age})")
                elif "< 60" in age_rest and user_age >= 60:
                    eligible = False
                    reasons.append(f"For individuals under 60 years (User age: {user_age})")
            
            # Health insurance check
            if scheme_code.upper() == "80D" and not has_health_insurance:
                eligible = False
                reasons.append("Requires active health insurance policy")
                
            # Education loan check
            if scheme_code.upper() == "80E" and not has_education_loan:
                eligible = False
                reasons.append("Requires active education loan")
                
            if eligible:
                reasons.append("Meets basic eligibility criteria")
                
            return {
                "success": True,
                "scheme_code": scheme_code,
                "eligible": eligible,
                "reasons": reasons
            }
        except Exception as e:
            self.logger.error(f"Error checking eligibility: {e}")
            return {
                "success": False,
                "error": str(e),
                "eligible": False,
                "reasons": [f"Internal error checking eligibility: {str(e)}"]
            }


# ============================================================================
# WEB SEARCH TOOL (Simplified - for demonstration)
# ============================================================================

class WebSearchTool:
    """Search for latest tax information and news."""
    
    def __init__(self):
        self.logger = logging.getLogger("tool.web_search")
        
        # Pre-indexed information (in production, use Tavily or similar)
        self.indexed_info = {
            "latest_tax_rules": [
                {
                    "title": "New tax rules for FY 2024-25",
                    "source": "Indian Income Tax Department",
                    "date": "2024-06-15",
                    "summary": "Updated tax brackets and deduction limits"
                },
                {
                    "title": "Changes in standard deduction",
                    "source": "CBDTOfficial",
                    "date": "2024-06-10",
                    "summary": "Standard deduction increased for salaried employees"
                }
            ],
            "government_schemes": [
                {
                    "name": "PMJDY - Jan Dhan Yojana",
                    "category": "Banking",
                    "description": "Universal banking access scheme"
                },
                {
                    "name": "PMSBY - Pradhan Mantri Suraksha Bima Yojana",
                    "category": "Insurance",
                    "description": "Accident insurance scheme"
                }
            ],
            "tax_deadlines": [
                {
                    "event": "ITR Filing Deadline",
                    "date": "2024-07-31",
                    "description": "Last date to file ITR for FY 2023-24"
                },
                {
                    "event": "Advance Tax Payment",
                    "date": "2024-06-15",
                    "description": "Q1 advance tax payment deadline"
                }
            ]
        }
    
    async def search_latest_tax_rules(self, keyword: str = "") -> Dict[str, Any]:
        """Search for latest tax rules and updates."""
        try:
            results = self.indexed_info.get("latest_tax_rules", [])
            
            if keyword:
                results = [r for r in results if keyword.lower() in r.get("summary", "").lower()]
            
            return {
                "success": True,
                "query": keyword,
                "results": results,
                "last_updated": datetime.utcnow().isoformat(),
                "note": "In production, integrate with Tavily API for real-time search"
            }
        except Exception as e:
            self.logger.error(f"Error searching tax rules: {e}")
            return {"success": False, "error": str(e)}
    
    async def search_government_schemes(self, keyword: str = "") -> Dict[str, Any]:
        """Search for government schemes and announcements."""
        try:
            results = self.indexed_info.get("government_schemes", [])
            
            if keyword:
                results = [
                    r for r in results
                    if (keyword.lower() in r.get("name", "").lower() or
                        keyword.lower() in r.get("description", "").lower())
                ]
            
            return {
                "success": True,
                "query": keyword,
                "results": results,
                "last_updated": datetime.utcnow().isoformat()
            }
        except Exception as e:
            self.logger.error(f"Error searching schemes: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_tax_deadlines(self) -> Dict[str, Any]:
        """Get important tax deadlines."""
        try:
            return {
                "success": True,
                "deadlines": self.indexed_info.get("tax_deadlines", []),
                "last_updated": datetime.utcnow().isoformat()
            }
        except Exception as e:
            self.logger.error(f"Error fetching deadlines: {e}")
            return {"success": False, "error": str(e)}