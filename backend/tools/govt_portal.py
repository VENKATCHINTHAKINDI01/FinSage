"""
Government Portal Integration Module
====================================

Simulates official Income Tax Department portal utilities (PAN verification, Form 26AS).
"""

import logging
import re
from typing import Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class GovtPortalClient:
    """Mock connector for official India income tax API gateway."""
    
    @staticmethod
    def verify_pan_details(pan_number: str) -> Dict[str, Any]:
        """
        Validate PAN (Permanent Account Number) format and return status.
        Format: 5 alphabets, 4 digits, 1 alphabet (e.g. ABCDE1234F).
        """
        try:
            pan_clean = pan_number.strip().upper()
            
            # Standard PAN regex pattern
            pan_pattern = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
            if not pan_pattern.match(pan_clean):
                return {
                    "success": False,
                    "error": "Invalid PAN format. Must be in standard 10-character alphanumeric format (e.g. ABCDE1234F)."
                }
                
            # Fifth character represents last name first letter. 
            # Fourth character represents card holder type (P = Individual, C = Company, H = HUF, F = Firm)
            holder_type_code = pan_clean[3]
            holder_types = {
                "P": "Individual",
                "C": "Company",
                "H": "Hindu Undivided Family (HUF)",
                "F": "Partnership Firm",
                "A": "Association of Persons",
                "T": "Trust"
            }
            holder_type = holder_types.get(holder_type_code, "Other/Unknown")
            
            return {
                "success": True,
                "pan": pan_clean,
                "result": {
                    "status": "Active & Linked",
                    "holder_type": holder_type,
                    "aadhaar_linked": True,
                    "verified_at": datetime.utcnow().isoformat()
                }
            }
        except Exception as e:
            logger.error(f"Error verifying PAN details: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def fetch_form_26as_statement(pan_number: str) -> Dict[str, Any]:
        """
        Fetch summary of Form 26AS (Tax Credit Statement) from income tax portal.
        """
        try:
            pan_clean = pan_number.strip().upper()
            
            # Simple PAN check
            pan_pattern = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
            if not pan_pattern.match(pan_clean):
                return {"success": False, "error": "Invalid PAN format"}
                
            return {
                "success": True,
                "pan": pan_clean,
                "financial_year": "2024-25",
                "result": {
                    "tds_deducted": [
                        {
                            "deductor_name": "Infosys Tech Corp Ltd",
                            "tan": "BLRI12345C",
                            "section": "192 (Salary)",
                            "amount_paid": 1200000.0,
                            "tds_deposited": 105000.0
                        },
                        {
                            "deductor_name": "Standard Chartered Bank",
                            "tan": "MUMI67890D",
                            "section": "194A (Interest other than securities)",
                            "amount_paid": 50000.0,
                            "tds_deposited": 5000.0
                        }
                    ],
                    "total_tds_credit": 110000.0,
                    "tcs_collected": [],
                    "advance_tax_paid": [
                        {
                            "challan_no": "1002345",
                            "bsr_code": "0210344",
                            "date_paid": "2024-09-14",
                            "amount": 25000.0
                        }
                    ],
                    "total_tax_credits": 135000.0,
                    "last_updated": datetime.utcnow().isoformat()
                }
            }
        except Exception as e:
            logger.error(f"Error fetching Form 26AS: {e}")
            return {"success": False, "error": str(e)}
