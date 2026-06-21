"""
PDF Parser Module
=================

Parses structured text and financial data from PDFs (e.g. Form 16, investment receipts).
"""

import logging
from typing import Dict, Any
import os

logger = logging.getLogger(__name__)


class PDFStatementParser:
    """Mock parser to extract income, TDS, and investment details from financial PDF documents."""
    
    @staticmethod
    def parse_investment_receipt(file_path: str) -> Dict[str, Any]:
        """
        Scan and parse investment receipts (ELSS mutual funds, NPS, PPF).
        """
        try:
            filename = os.path.basename(file_path).lower()
            
            # Simulated parsing results based on filenames
            if "elss" in filename:
                return {
                    "success": True,
                    "document_type": "ELSS Receipt",
                    "result": {
                        "scheme_name": "ELSS Tax Saver Growth Fund",
                        "folio_no": "FOL1290384",
                        "transaction_date": "2024-03-12",
                        "amount": 50000.0,
                        "units": 401.6,
                        "nav": 124.50,
                        "section_eligibility": "80C"
                    }
                }
            elif "nps" in filename:
                return {
                    "success": True,
                    "document_type": "NPS Receipt",
                    "result": {
                        "scheme_name": "SBI Pension Fund Scheme E",
                        "pran": "PRN903841029",
                        "transaction_date": "2024-02-18",
                        "amount": 30000.0,
                        "section_eligibility": "80CCD(1B)"
                    }
                }
                
            return {
                "success": True,
                "document_type": "General Investment Receipt",
                "result": {
                    "scheme_name": "Mock Tax Saving Fund",
                    "transaction_date": "2024-01-15",
                    "amount": 10000.0,
                    "section_eligibility": "80C"
                }
            }
        except Exception as e:
            logger.error(f"Error parsing PDF investment receipt: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def parse_form16(file_path: str) -> Dict[str, Any]:
        """
        Simulate parsing of Form 16 Part B (Salaried employee tax certificate).
        """
        try:
            return {
                "success": True,
                "document_type": "Form 16 - Certificate of TDS on Salary",
                "result": {
                    "employer": {
                        "name": "Infosys Tech Corp Ltd",
                        "tan": "BLRI12345C",
                        "pan": "AAACI9032A"
                    },
                    "employee": {
                        "name": "John Doe",
                        "pan": "ABCDE1234F"
                    },
                    "assessment_year": "2025-26",
                    "financial_year": "2024-25",
                    "salary_breakdown": {
                        "gross_salary": 1200000.0,
                        "exempt_allowances": 150000.0,
                        "standard_deduction": 50000.0,
                        "professional_tax": 2400.0,
                        "taxable_salary": 997600.0
                    },
                    "chapter_vi_a_deductions": {
                        "80C": 150000.0,
                        "80D": 25000.0,
                        "80CCD": 0.0
                    },
                    "tax_computations": {
                        "total_taxable_income": 822600.0,
                        "gross_tax_liability": 74520.0,
                        "surcharge": 0.0,
                        "education_cess": 2980.80,
                        "total_tax_payable": 77500.80,
                        "tds_deducted": 77500.0
                    }
                }
            }
        except Exception as e:
            logger.error(f"Error parsing Form 16 PDF: {e}")
            return {"success": False, "error": str(e)}
