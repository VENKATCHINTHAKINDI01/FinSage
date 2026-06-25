"""
Service to calculate and track financial health scores.
"""

import logging
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.db.orm_models import FinancialHealthScore

logger = logging.getLogger(__name__)


class FinancialHealthScorer:
    """
    Calculate financial health score.
    
    5 Factors (20% each):
    1. Tax Efficiency (20%)
    2. Deduction Optimization (20%)
    3. Savings Potential (20%)
    4. Compliance Status (20%)
    5. Investment Diversity (20%)
    
    Features:
    • Score breakdown
    • Trend analysis
    • Recommendations
    • Database persistence
    """
    
    def __init__(self, db: Optional[Session] = None):
        self.name = "financial_health_scorer"
        self.db = db
        self.logger = logging.getLogger(f"service.{self.name}")
    
    def set_db(self, db: Session):
        """Set database session."""
        self.db = db
        return self
    
    async def calculate_health_score(
        self,
        user_id: str,
        financial_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Calculate overall financial health score.
        
        Workflow:
        1. Calculate 5 factor scores
        2. Weight each at 20%
        3. Get overall score
        4. Analyze trend
        5. Generate recommendations
        6. Save to database
        """
        try:
            self.logger.info(f"Calculating health score for user {user_id}")
            
            # STEP 1: Calculate individual factor scores
            tax_efficiency_score = self._calculate_tax_efficiency(financial_data)
            deduction_optimization_score = self._calculate_deduction_optimization(financial_data)
            savings_potential_score = self._calculate_savings_potential(financial_data)
            compliance_status_score = self._calculate_compliance_status(financial_data)
            investment_diversity_score = self._calculate_investment_diversity(financial_data)
            
            # STEP 2: Calculate overall score (weighted average)
            overall_score = int(
                (tax_efficiency_score * 0.20) +
                (deduction_optimization_score * 0.20) +
                (savings_potential_score * 0.20) +
                (compliance_status_score * 0.20) +
                (investment_diversity_score * 0.20)
            )
            
            # STEP 3: Get trend vs last month
            trend = await self._get_trend(user_id, overall_score)
            
            # STEP 4: Generate recommendations
            recommendations = self._generate_recommendations(
                tax_efficiency_score,
                deduction_optimization_score,
                savings_potential_score,
                compliance_status_score,
                investment_diversity_score
            )
            
            # STEP 5: Create breakdown
            breakdown = {
                "tax_efficiency": {
                    "score": tax_efficiency_score,
                    "weight": "20%",
                    "description": "How efficiently you manage tax liability"
                },
                "deduction_optimization": {
                    "score": deduction_optimization_score,
                    "weight": "20%",
                    "description": "How well you utilize available deductions"
                },
                "savings_potential": {
                    "score": savings_potential_score,
                    "weight": "20%",
                    "description": "Potential for additional tax savings"
                },
                "compliance_status": {
                    "score": compliance_status_score,
                    "weight": "20%",
                    "description": "Your tax compliance readiness"
                },
                "investment_diversity": {
                    "score": investment_diversity_score,
                    "weight": "20%",
                    "description": "Diversification of investments for tax benefits"
                }
            }
            
            # STEP 6: Get health status
            health_status = self._get_health_status(overall_score)
            
            result = {
                "overall_score": overall_score,
                "health_status": health_status,
                "breakdown": breakdown,
                "trend": trend,
                "recommendations": recommendations,
                "score_date": datetime.utcnow().isoformat(),
                
                "action_items": [
                    f"Priority 1: {self._get_priority_action(overall_score, breakdown)}"
                ] if overall_score < 80 else [
                    "Maintain current practices",
                    "Monitor quarterly for changes"
                ]
            }
            
            # STEP 7: Save to database
            db_record = None
            if user_id:
                db_record = await self._save_to_database(user_id, result, breakdown)
            
            response = {
                "success": True,
                "result": result,
                "confidence": 0.90
            }
            if db_record is not None:
                response["db_record"] = db_record
                
            return response
        
        except Exception as e:
            self.logger.error(f"Error calculating health score: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    def _calculate_tax_efficiency(self, data: Dict[str, Any]) -> int:
        """
        Calculate tax efficiency score (0-100).
        
        Factors:
        • Effective tax rate (lower is better)
        • Tax optimization done
        • TDS proper credit
        """
        score = 100
        
        # Deduct for high effective tax rate
        effective_rate = data.get("effective_tax_rate")
        if effective_rate is None:
            # Fallback calculation if key is not directly present
            gross_income = data.get("gross_income") or data.get("annual_income", 0)
            tax_liability = data.get("tax_liability", 0)
            if gross_income > 0:
                effective_rate = (float(tax_liability) / float(gross_income)) * 100
            else:
                effective_rate = 20
        
        if effective_rate > 30:
            score -= 30
        elif effective_rate > 20:
            score -= 15
        elif effective_rate > 10:
            score -= 5
        
        # Deduct for TDS mismatch
        if data.get("tds_mismatch", False):
            score -= 15
        
        # Bonus for optimization done
        if data.get("optimization_done", False):
            score += 10
        
        return max(0, min(100, score))
    
    def _calculate_deduction_optimization(self, data: Dict[str, Any]) -> int:
        """
        Calculate deduction optimization score (0-100).
        
        Factors:
        • % of max deduction used
        • Number of deductions claimed
        • Deduction validity
        """
        score = 50  # Start at 50
        
        current_deductions = data.get("total_deductions")
        if current_deductions is None:
            deductions = data.get("deductions", {})
            if isinstance(deductions, dict):
                current_deductions = sum(
                    float(val.get("amount", 0)) if isinstance(val, dict) else float(val)
                    for val in deductions.values()
                )
            elif isinstance(deductions, (list, tuple)):
                current_deductions = sum(float(val) for val in deductions)
            else:
                current_deductions = float(deductions) if deductions else 0.0

        max_deduction_limit = 1500000  # 80C + 80D + others combined
        
        # Score based on deduction usage
        deduction_ratio = (current_deductions / max_deduction_limit) if max_deduction_limit > 0 else 0
        
        if deduction_ratio >= 0.8:
            score += 50  # Using 80%+ of available
        elif deduction_ratio >= 0.6:
            score += 35
        elif deduction_ratio >= 0.4:
            score += 20
        
        # Bonus for multiple deductions
        deduction_count = data.get("deduction_count")
        if deduction_count is None:
            deductions = data.get("deductions", {})
            deduction_count = len(deductions) if isinstance(deductions, dict) else (1 if deductions else 0)

        if deduction_count >= 5:
            score += 10
        elif deduction_count >= 3:
            score += 5
        
        return max(0, min(100, score))
    
    def _calculate_savings_potential(self, data: Dict[str, Any]) -> int:
        """
        Calculate savings potential score (0-100).
        
        Factors:
        • Available deduction headroom
        • Investment opportunities
        • Income growth potential
        """
        score = 50
        
        current_deductions = data.get("total_deductions")
        if current_deductions is None:
            deductions = data.get("deductions", {})
            if isinstance(deductions, dict):
                current_deductions = sum(
                    float(val.get("amount", 0)) if isinstance(val, dict) else float(val)
                    for val in deductions.values()
                )
            elif isinstance(deductions, (list, tuple)):
                current_deductions = sum(float(val) for val in deductions)
            else:
                current_deductions = float(deductions) if deductions else 0.0

        max_deduction = 1500000
        
        # Headroom available
        headroom = max_deduction - current_deductions
        headroom_ratio = (headroom / max_deduction) if max_deduction > 0 else 0
        
        if headroom_ratio >= 0.5:
            score += 50  # High potential
        elif headroom_ratio >= 0.3:
            score += 30
        elif headroom_ratio >= 0.1:
            score += 15
        
        # Investment opportunities
        investment_options = data.get("investment_options_available", 0)
        if investment_options >= 5:
            score += 10
        
        return max(0, min(100, score))
    
    def _calculate_compliance_status(self, data: Dict[str, Any]) -> int:
        """
        Calculate compliance status score (0-100).
        
        Factors:
        • Compliance score
        • Red flags count
        • Audit readiness
        • Documentation
        """
        # Start with compliance score
        compliance_score = data.get("compliance_score", 70)
        score = compliance_score
        
        # Deduct for red flags
        red_flags = data.get("red_flags", 0)
        if red_flags > 5:
            score -= 20
        elif red_flags > 3:
            score -= 15
        elif red_flags > 1:
            score -= 10
        
        # Bonus for audit readiness
        if data.get("audit_ready", False):
            score += 15
        
        # Deduct for missing documents
        missing_docs = data.get("missing_documents", 0)
        if missing_docs > 5:
            score -= 15
        
        return max(0, min(100, score))
    
    def _calculate_investment_diversity(self, data: Dict[str, Any]) -> int:
        """
        Calculate investment diversity score (0-100).
        
        Factors:
        • Number of investment types
        • Tax-optimized investments
        • Asset allocation
        """
        score = 50
        
        invest_data = data.get("investments", {})
        
        investments = {
            "life_insurance": data.get("life_insurance", False) or (isinstance(invest_data, dict) and (float(invest_data.get("life_insurance", 0)) > 0 or float(invest_data.get("insurance", 0)) > 0)),
            "mutual_funds": data.get("mutual_funds", False) or (isinstance(invest_data, dict) and (float(invest_data.get("mutual_funds", 0)) > 0 or float(invest_data.get("elss", 0)) > 0 or float(invest_data.get("mutual_fund", 0)) > 0)),
            "ppf": data.get("ppf", False) or (isinstance(invest_data, dict) and float(invest_data.get("ppf", 0)) > 0),
            "nsc": data.get("nsc", False) or (isinstance(invest_data, dict) and float(invest_data.get("nsc", 0)) > 0),
            "health_insurance": data.get("health_insurance", False) or (isinstance(invest_data, dict) and float(invest_data.get("health_insurance", 0)) > 0),
            "nps": data.get("nps", False) or (isinstance(invest_data, dict) and float(invest_data.get("nps", 0)) > 0),
            "fixed_deposits": data.get("fixed_deposits", False) or (isinstance(invest_data, dict) and (float(invest_data.get("fixed_deposits", 0)) > 0 or float(invest_data.get("fd", 0)) > 0)),
            "savings_account": data.get("savings_account", False) or (isinstance(invest_data, dict) and float(invest_data.get("savings_account", 0)) > 0)
        }
        
        investment_count = sum(1 for v in investments.values() if v)
        
        if investment_count >= 6:
            score += 50
        elif investment_count >= 4:
            score += 35
        elif investment_count >= 2:
            score += 20
        else:
            score += 5
        
        return max(0, min(100, score))
    
    async def _get_trend(self, user_id: str, current_score: int) -> Dict[str, Any]:
        """
        Get trend vs last month.
        """
        try:
            if not self.db:
                return {
                    "status": "First calculation",
                    "previous_score": None,
                    "change": None
                }
            
            # Get last month's score
            one_month_ago = datetime.utcnow() - timedelta(days=30)
            
            if hasattr(self.db, "execute"):
                # AsyncSession style
                query = (
                    select(FinancialHealthScore)
                    .where(FinancialHealthScore.user_id == user_id)
                    .where(FinancialHealthScore.score_date < one_month_ago)
                    .order_by(FinancialHealthScore.score_date.desc())
                    .limit(1)
                )
                res = await self.db.execute(query)
                last_score = res.scalars().first()
            else:
                # Sync Session style
                last_score = self.db.query(FinancialHealthScore).filter(
                    FinancialHealthScore.user_id == user_id,
                    FinancialHealthScore.score_date < one_month_ago
                ).order_by(FinancialHealthScore.score_date.desc()).first()
            
            if not last_score:
                return {
                    "status": "First calculation",
                    "previous_score": None,
                    "change": None
                }
            
            change = current_score - last_score.overall_score
            direction = "↑" if change > 0 else ("↓" if change < 0 else "→")
            
            return {
                "status": f"{direction} {abs(change)} points",
                "previous_score": last_score.overall_score,
                "current_score": current_score,
                "change": change,
                "direction": direction,
                "last_calculated": last_score.score_date.isoformat()
            }
        
        except Exception as e:
            self.logger.error(f"Error getting trend: {e}")
            return {"status": "Unable to calculate trend"}
    
    def _generate_recommendations(
        self,
        tax_eff: int,
        deduction_opt: int,
        savings_pot: int,
        compliance: int,
        investment_div: int
    ) -> List[str]:
        """Generate personalized recommendations."""
        recommendations = []
        
        # Tax efficiency recommendations
        if tax_eff < 60:
            recommendations.append("🔴 URGENT: Review tax planning strategy with CA")
        elif tax_eff < 80:
            recommendations.append("🟡 Consider advanced tax planning techniques")
        
        # Deduction optimization
        if deduction_opt < 60:
            recommendations.append("🔴 Maximize available deductions before year-end")
        elif deduction_opt < 80:
            recommendations.append("🟡 Explore additional deduction opportunities")
        
        # Savings potential
        if savings_pot > 70:
            recommendations.append("💰 Significant savings potential available - Act now!")
        
        # Compliance
        if compliance < 70:
            recommendations.append("🔴 Address compliance issues immediately")
        elif compliance < 85:
            recommendations.append("🟡 Improve compliance documentation")
        
        # Investment diversity
        if investment_div < 60:
            recommendations.append("📊 Diversify investments for better tax optimization")
        
        return recommendations
    
    def _get_health_status(self, score: int) -> Dict[str, Any]:
        """Get health status based on score."""
        if score >= 85:
            return {
                "level": "Excellent",
                "emoji": "🟢",
                "message": "Outstanding financial health!",
                "color": "#10B981"
            }
        elif score >= 70:
            return {
                "level": "Good",
                "emoji": "🟡",
                "message": "Good health with room for improvement",
                "color": "#F59E0B"
            }
        elif score >= 50:
            return {
                "level": "Fair",
                "emoji": "🟠",
                "message": "Needs attention in several areas",
                "color": "#F97316"
            }
        else:
            return {
                "level": "Poor",
                "emoji": "🔴",
                "message": "Critical issues need immediate attention",
                "color": "#EF4444"
            }
    
    def _get_priority_action(self, score: int, breakdown: Dict[str, Any]) -> str:
        """Get highest priority action."""
        lowest_factor = min(
            breakdown.items(),
            key=lambda x: x[1]["score"]
        )
        
        return f"Improve {lowest_factor[0]} (currently {lowest_factor[1]['score']}/100)"
    
    async def _save_to_database(
        self,
        user_id: str,
        result: Dict[str, Any],
        breakdown: Dict[str, Any]
    ) -> FinancialHealthScore:
        """Save health score to database."""
        try:
            trend_val = None
            if isinstance(result.get("trend"), dict):
                trend_val = result["trend"].get("change")
            elif isinstance(result.get("trend"), int):
                trend_val = result["trend"]
                
            health_score = FinancialHealthScore(
                user_id=user_id,
                overall_score=result["overall_score"],
                tax_efficiency_score=breakdown["tax_efficiency"]["score"],
                deduction_optimization_score=breakdown["deduction_optimization"]["score"],
                savings_potential_score=breakdown["savings_potential"]["score"],
                compliance_status_score=breakdown["compliance_status"]["score"],
                investment_diversity_score=breakdown["investment_diversity"]["score"],
                breakdown=breakdown,
                recommendations=result.get("recommendations"),
                trend_vs_last_month=trend_val
            )
            
            if self.db:
                self.db.add(health_score)
                if hasattr(self.db, "commit"):
                    res = self.db.commit()
                    if asyncio.iscoroutine(res):
                        await res
                self.logger.info(f"Health score saved for user {user_id}")
                
            return health_score
        
        except Exception as e:
            self.logger.error(f"Error saving to database: {e}")
            if self.db and hasattr(self.db, "rollback"):
                res = self.db.rollback()
                if asyncio.iscoroutine(res):
                    await res
            raise e

    async def calculate_and_save_score(
        self,
        user_id: str,
        profile_data: Dict[str, Any]
    ) -> FinancialHealthScore:
        """
        Calculate and persist health score (backward compatible wrapper).
        """
        res = await self.calculate_health_score(user_id, profile_data)
        if not res.get("success"):
            raise Exception(res.get("error", "Failed to calculate health score"))
        
        return res["db_record"]
