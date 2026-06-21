"""
Financial API Integration Module
================================

Retrieves external account balances, bank statements, and stock/mutual fund prices.
"""

import logging
from typing import Dict, Any, List
import random
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class FinancialAPIClient:
    """Mock API client for third-party bank accounts and live market valuations."""
    
    @staticmethod
    async def fetch_live_market_data(ticker: str) -> Dict[str, Any]:
        """
        Fetch current market price and details for a mutual fund or stock.
        """
        try:
            ticker_upper = ticker.strip().upper()
            logger.info(f"Requesting live market data for ticker: {ticker_upper}")
            
            # Simple mock database
            market_db = {
                "ELSS_MAX_GROWTH": {
                    "name": "ELSS Tax Saver Max Growth Fund",
                    "nav": 124.50,
                    "type": "Mutual Fund",
                    "category": "Tax Saver ELSS",
                    "1y_return": 18.2,
                    "expense_ratio": 1.15
                },
                "NPS_SCHEME_E": {
                    "name": "NPS Scheme E (Equity) - SBI Pension Fund",
                    "nav": 42.15,
                    "type": "Pension Fund",
                    "category": "National Pension Scheme",
                    "1y_return": 14.5,
                    "expense_ratio": 0.01
                },
                "INFY": {
                    "name": "Infosys Limited",
                    "price": 1450.00,
                    "type": "Stock",
                    "category": "Information Technology",
                    "1y_return": 12.8,
                    "dividend_yield": 2.4
                },
                "TCS": {
                    "name": "Tata Consultancy Services",
                    "price": 3820.00,
                    "type": "Stock",
                    "category": "Information Technology",
                    "1y_return": 15.1,
                    "dividend_yield": 2.1
                }
            }
            
            if ticker_upper in market_db:
                data = market_db[ticker_upper].copy()
                data["last_updated"] = datetime.utcnow().isoformat()
                logger.info(f"Successfully retrieved market data for ticker {ticker_upper}: {data}")
                return {"success": True, "ticker": ticker_upper, "result": data}
            
            # Fallback for unknown tickers
            price = round(random.uniform(50, 5000), 2)
            logger.info(f"Ticker {ticker_upper} not found in market database, returning mock price: ₹{price}")
            return {
                "success": True,
                "ticker": ticker_upper,
                "result": {
                    "name": f"Mock Asset ({ticker_upper})",
                    "price": price,
                    "nav": price,
                    "type": "Unknown",
                    "category": "General",
                    "1y_return": round(random.uniform(5.0, 25.0), 1),
                    "last_updated": datetime.utcnow().isoformat()
                }
            }
        except Exception as e:
            logger.error(f"Error fetching market data: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    async def fetch_bank_statements(
        bank_name: str,
        account_id: str
    ) -> Dict[str, Any]:
        """
        Mock fetching transactions list and summary from user's linked bank account.
        """
        try:
            logger.info(f"Fetching bank statements for bank: {bank_name}, account ID: {account_id}")
            today = datetime.now()
            transactions = []
            
            # Mock transaction generator
            descriptions = [
                ("Salary Credit", 120000.0, "credit"),
                ("Office Co-Working Rent", 15000.0, "debit"),
                ("Amazon Web Services", 8500.0, "debit"),
                ("LIC Premium Payment", 22000.0, "debit"),
                ("Starbucks Coffee", 450.0, "debit"),
                ("HDFC Bank Home Loan EMI", 35000.0, "debit"),
                ("NPS Contribution Direct", 10000.0, "debit"),
                ("Apollo Pharmacy", 1200.0, "debit")
            ]
            
            total_credits = 0.0
            total_debits = 0.0
            
            for i, desc_pair in enumerate(descriptions):
                desc, amount, tx_type = desc_pair
                tx_date = today - timedelta(days=i * 3)
                
                transactions.append({
                    "tx_id": f"tx_{account_id[-4:]}_{i:03d}",
                    "date": tx_date.date().isoformat(),
                    "description": desc,
                    "amount": amount,
                    "type": tx_type
                })
                
                if tx_type == "credit":
                    total_credits += amount
                else:
                    total_debits += amount
                    
            logger.info(f"Successfully fetched {len(transactions)} transactions for bank: {bank_name}, account ID: {account_id}")
            return {
                "success": True,
                "bank_name": bank_name,
                "account_id": account_id,
                "summary": {
                    "current_balance": 145200.50,
                    "total_credits": total_credits,
                    "total_debits": total_debits,
                    "statement_period": f"Last 30 Days"
                },
                "transactions": transactions
            }
        except Exception as e:
            logger.error(f"Error fetching bank statement: {e}")
            return {"success": False, "error": str(e)}
