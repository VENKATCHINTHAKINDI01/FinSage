"""
Price Intelligence Agent
========================

Handles inflation indexation (CII) and tax-adjusted yield comparisons.
"""

import time
import logging
from typing import Dict, Any, List
from datetime import datetime

from backend.agents.base_agent import TaxAgent, AgentOutput

logger = logging.getLogger(__name__)


class PriceIntelligenceAgent(TaxAgent):
    """
    Compare investment products by post-tax yields and calculate cost inflation indexation:
    
    • Cost Inflation Index (CII) lookups & capital gains indexation (LTCG)
    • Post-tax yield comparison (Fixed Deposits, ELSS, Gold, SGBs, Debt Funds)
    • Asset purchasing optimization insights
    """
    
    # Cost Inflation Index (CII) values from official Income Tax department (FY 2001-02 onwards)
    CII_TABLE = {
        "2001-02": 100,
        "2002-03": 105,
        "2003-04": 109,
        "2004-05": 113,
        "2005-06": 117,
        "2006-07": 122,
        "2007-08": 129,
        "2008-09": 137,
        "2009-10": 148,
        "2010-11": 167,
        "2011-12": 184,
        "2012-13": 200,
        "2013-14": 220,
        "2014-15": 240,
        "2015-16": 254,
        "2016-17": 264,
        "2017-18": 272,
        "2018-19": 280,
        "2019-20": 289,
        "2020-21": 301,
        "2021-22": 317,
        "2022-23": 331,
        "2023-24": 348,
        "2024-25": 363
    }
    
    def __init__(self):
        super().__init__("price_intelligence_agent", "price_intelligence")
        
    async def execute(
        self,
        user_query: str,
        user_context: Dict[str, Any],
        tools=None,
        **kwargs
    ) -> AgentOutput:
        """
        Analyze capital gains indexation or calculate post-tax yields.
        """
        start_time = time.time()
        if tools is not None:
            self.set_tools(tools)
            
        try:
            self.logger.info(f"Starting price intelligence analysis for: {user_query}")
            
            # Fetch user profile/investments if available
            user_profile = {}
            if self.tools:
                profile_res = await self.call_tool(
                    "get_user_profile",
                    user_id=user_context.get("user_id", "unknown")
                )
                if profile_res.get("success"):
                    user_profile = profile_res.get("result", {})
                    
            annual_income = float(user_profile.get("financial_profile", {}).get("annual_income", 0)) or float(user_context.get("annual_income", 0)) or 1000000.0
            
            # 1. Determine marginal tax slab rate (for yield tax calculations)
            tax_rate = 0.30
            if annual_income <= 300000:
                tax_rate = 0.00
            elif annual_income <= 700000:
                tax_rate = 0.05
            elif annual_income <= 1000000:
                tax_rate = 0.10
            elif annual_income <= 1200000:
                tax_rate = 0.15
            elif annual_income <= 1500000:
                tax_rate = 0.20
            
            # 2. Check if query is about indexation / capital gains
            is_indexation_query = any(word in user_query.lower() for word in ["index", "cii", "inflation", "gain", "sell", "buy", "purchase"])
            
            result = {}
            recommendations = []
            
            if is_indexation_query:
                # Capital gains calculation using CII indexation
                asset_type = user_context.get("asset_type", "real_estate") # real_estate, gold, debt_fund, etc.
                purchase_year = user_context.get("purchase_year", "2015-16")
                sell_year = user_context.get("sell_year", "2024-25")
                purchase_price = float(user_context.get("purchase_price") or 5000000.0)
                sell_price = float(user_context.get("sale_price") or 8000000.0)
                
                cii_purchase = self.CII_TABLE.get(purchase_year, 254)
                cii_sell = self.CII_TABLE.get(sell_year, 363)
                
                indexed_cost = purchase_price * (cii_sell / cii_purchase)
                capital_gain = sell_price - indexed_cost
                
                # Standard LTCG tax rate (20% with indexation for real estate/gold)
                ltcg_tax = max(0.0, capital_gain * 0.20)
                
                result = {
                    "calculation_type": "indexation_ltcg",
                    "asset_type": asset_type,
                    "purchase_year": purchase_year,
                    "sell_year": sell_year,
                    "purchase_price": purchase_price,
                    "sale_price": sell_price,
                    "cii_purchase": cii_purchase,
                    "cii_sell": cii_sell,
                    "indexed_cost": indexed_cost,
                    "capital_gains": capital_gain,
                    "estimated_ltcg_tax": ltcg_tax
                }
                
                recommendations.append(
                    f"Your indexed cost of acquisition is ₹{indexed_cost:,.2f} (inflated from ₹{purchase_price:,.2f} using CII values)."
                )
                recommendations.append(
                    f"The net taxable capital gains after indexation is ₹{capital_gain:,.2f}. Estimated tax (20%): ₹{ltcg_tax:,.2f}."
                )
                if asset_type == "real_estate" and capital_gain > 0:
                    recommendations.append(
                        "You can save this tax by reinvesting the capital gains under Section 54 (buying another house) "
                        "or Section 54EC (Capital Gains Bonds like REC/NHAI, up to ₹50 Lakhs limit)."
                    )
            else:
                # Tax-adjusted yields comparison
                gross_investment = float(user_context.get("investment_amount") or 100000.0)
                
                # Asset class projections
                # 1. FD: Gross 7.5%, Interest taxed at slab
                fd_gross = 0.075
                fd_net = fd_gross * (1 - tax_rate)
                
                # 2. ELSS: Gross 12%, LTCG taxed at 10% (exemption of 1L ignored for safety)
                elss_gross = 0.12
                elss_net = elss_gross * (1 - 0.10)
                
                # 3. Sovereign Gold Bonds (SGB): Gross 2.5% yield + 6% gold return. 
                # Interest taxed at slab. Capital gains on maturity are tax-exempt!
                sgb_gross = 0.085
                sgb_net = (0.025 * (1 - tax_rate)) + 0.06
                
                # 4. Debt Mutual Funds (post-2023): Gross 7%, gains taxed at slab
                debt_gross = 0.07
                debt_net = debt_gross * (1 - tax_rate)
                
                yield_comparison = [
                    {"instrument": "ELSS (Tax Saving Mutual Fund)", "gross_yield": f"{elss_gross*100:.2f}%", "post_tax_yield": f"{elss_net*100:.2f}%", "tax_treatment": "10% LTCG above ₹1.25L exemption limit"},
                    {"instrument": "Sovereign Gold Bond (SGB)", "gross_yield": f"{sgb_gross*100:.2f}%", "post_tax_yield": f"{sgb_net*100:.2f}%", "tax_treatment": "Interest taxed at slab, capital gains fully tax-free on maturity"},
                    {"instrument": "Fixed Deposit (FD)", "gross_yield": f"{fd_gross*100:.2f}%", "post_tax_yield": f"{fd_net*100:.2f}%", "tax_treatment": "Interest fully taxable at your slab rate"},
                    {"instrument": "Debt Mutual Fund", "gross_yield": f"{debt_gross*100:.2f}%", "post_tax_yield": f"{debt_net*100:.2f}%", "tax_treatment": "Taxed at slab rate (no indexation benefit for fresh purchases)"}
                ]
                
                result = {
                    "calculation_type": "post_tax_yields",
                    "gross_investment": gross_investment,
                    "marginal_tax_rate": tax_rate,
                    "yield_comparison": yield_comparison
                }
                
                recommendations.append(
                    f"Based on your marginal tax slab of {tax_rate*100:.0f}%, FDs and Debt Funds have a low post-tax yield of "
                    f"{(fd_net if fd_net > debt_net else debt_net)*100:.2f}%."
                )
                recommendations.append(
                    f"ELSS offers the highest post-tax yield potential ({elss_net*100:.2f}%) and provides Section 80C deductions."
                )
                recommendations.append(
                    f"Sovereign Gold Bonds (SGB) are highly tax-efficient ({sgb_net*100:.2f}% post-tax) as capital gains on maturity are completely exempt from tax."
                )
                
            result["recommendations"] = recommendations
            
            execution_time = (time.time() - start_time) * 1000
            
            return self._create_output(
                result=result,
                status="success",
                confidence=0.88,
                reasoning="Calculated cost inflation indexation and compared tax-adjusted yields.",
                execution_time_ms=execution_time
            )
            
        except Exception as e:
            self.logger.error(f"Error in PriceIntelligenceAgent: {e}", exc_info=True)
            execution_time = (time.time() - start_time) * 1000
            return self._create_output(
                result={"error": str(e)},
                status="error",
                confidence=0.0,
                reasoning=f"Failure evaluating investment yield options: {str(e)}",
                execution_time_ms=execution_time
            )
