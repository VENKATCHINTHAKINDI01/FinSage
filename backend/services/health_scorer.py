"""
Service to calculate and track financial health scores.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.orm_models import FinancialHealthScore, ComplianceReport


class FinancialHealthScorer:
    """
    Calculate and save financial health score based on 5 components:
    1. Tax Efficiency (20%)
    2. Deduction Optimization (20%)
    3. Savings Potential (20%)
    4. Compliance Status (20%)
    5. Investment Diversity (20%)
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.logger = logging.getLogger("service.financial_health_scorer")

    async def calculate_and_save_score(
        self,
        user_id: str,
        profile_data: Dict[str, Any]
    ) -> FinancialHealthScore:
        """
        Calculate and persist health score.
        
        profile_data should contain:
          - annual_income (float)
          - deductions (dict of category: amount)
          - investments (dict of type: amount)
          - tax_liability (float)
        """
        try:
            annual_income = float(profile_data.get("annual_income", 0))
            deductions = profile_data.get("deductions", {})
            investments = profile_data.get("investments", {})
            tax_liability = float(profile_data.get("tax_liability", 0))
            
            # Step 1: Calculate Tax Efficiency (20%)
            # Ratio of tax liability to gross income. Lower tax ratio relative to slab represents higher efficiency.
            if annual_income > 0:
                tax_ratio = tax_liability / annual_income
                tax_efficiency = max(0, min(100, int((1.0 - tax_ratio * 3) * 100)))
            else:
                tax_efficiency = 100
                
            # Step 2: Calculate Deduction Optimization (20%)
            # Measures how much of the standard deduction sections (80C, 80D) is utilized
            sec_80c = 0.0
            sec_80d = 0.0
            
            # Extract deductions from dictionary
            for cat, details in deductions.items():
                amt = float(details.get("amount", 0)) if isinstance(details, dict) else float(details)
                if "80c" in cat.lower():
                    sec_80c += amt
                elif "80d" in cat.lower():
                    sec_80d += amt
            
            opt_80c = min(1.0, sec_80c / 150000.0) if sec_80c > 0 else 0.0
            opt_80d = min(1.0, sec_80d / 50000.0) if sec_80d > 0 else 0.0
            deduction_optimization = int((opt_80c * 0.7 + opt_80d * 0.3) * 100)
            
            # Step 3: Calculate Savings Potential (20%)
            # Scored higher if they have minimized unused deductions room
            unused_80c = max(0.0, 150000.0 - sec_80c)
            unused_80d = max(0.0, 50000.0 - sec_80d)
            total_unused = unused_80c + unused_80d
            savings_potential = max(10, min(100, int(100 - (total_unused / 2000.0))))
            
            # Step 4: Calculate Compliance Status (20%)
            # Load from compliance report if present
            query = (
                select(ComplianceReport)
                .where(ComplianceReport.user_id == user_id)
                .order_by(ComplianceReport.created_at.desc())
                .limit(1)
            )
            result = await self.db.execute(query)
            report = result.scalars().first()
            compliance_status = report.compliance_score if report else 90
            
            # Step 5: Calculate Investment Diversity (20%)
            # Diversity score based on distribution across categories
            invest_types = set()
            for key, val in investments.items():
                if float(val) > 0:
                    invest_types.add(key.lower())
            
            diversity_count = len(invest_types)
            if diversity_count >= 3:
                investment_diversity = 100
            elif diversity_count == 2:
                investment_diversity = 75
            elif diversity_count == 1:
                investment_diversity = 50
            else:
                investment_diversity = 20
                
            # Step 6: Calculate Overall Weighted Score (20% each)
            overall_score = int(
                tax_efficiency * 0.20 +
                deduction_optimization * 0.20 +
                savings_potential * 0.20 +
                compliance_status * 0.20 +
                investment_diversity * 0.20
            )
            
            # Step 7: Calculate Trend vs Last Month
            last_month_query = (
                select(FinancialHealthScore)
                .where(FinancialHealthScore.user_id == user_id)
                .order_by(FinancialHealthScore.score_date.desc())
                .limit(1)
            )
            lm_res = await self.db.execute(last_month_query)
            last_score = lm_res.scalars().first()
            trend = (overall_score - last_score.overall_score) if last_score else 0
            
            breakdown = {
                "tax_efficiency": tax_efficiency,
                "deduction_optimization": deduction_optimization,
                "savings_potential": savings_potential,
                "compliance_status": compliance_status,
                "investment_diversity": investment_diversity
            }
            
            recommendations = []
            if tax_efficiency < 70:
                recommendations.append("Consider restructuring your salary package or investment streams to improve tax efficiency.")
            if deduction_optimization < 80:
                recommendations.append(f"Optimize Section 80C/80D limits. You have ₹{total_unused:,.2f} of unused deduction limit left.")
            if investment_diversity < 60:
                recommendations.append("Diversify investments across ELSS, PPF, and National Pension Scheme (NPS) for balanced tax-benefit benefits.")
            if not recommendations:
                recommendations.append("Excellent financial health! Maintain your current tax and investment optimizations.")
                
            health_score = FinancialHealthScore(
                user_id=user_id,
                overall_score=overall_score,
                tax_efficiency_score=tax_efficiency,
                deduction_optimization_score=deduction_optimization,
                savings_potential_score=savings_potential,
                compliance_status_score=compliance_status,
                investment_diversity_score=investment_diversity,
                breakdown=breakdown,
                recommendations=recommendations,
                trend_vs_last_month=trend
            )
            
            self.db.add(health_score)
            await self.db.commit()
            self.logger.info(f"Saved financial health score of {overall_score} for user {user_id}")
            return health_score
            
        except Exception as e:
            self.logger.error(f"Error calculating score: {e}", exc_info=True)
            await self.db.rollback()
            raise e
