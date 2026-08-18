"""
Alert Engine Module
===================

Proactive alert and notifications generator for tax planning.
"""

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class TaxAlertEngine:
    """Generates tax optimization warnings and monitors key filing deadlines."""

    @staticmethod
    def generate_tax_saving_alerts(
        investments: dict[str, float],
        deductions: dict[str, float],
        current_taxable_income: float = 0.0,
        fy: str | None = None,
        age: int = 0,
    ) -> dict[str, Any]:
        """
        Generate optimization suggestions and alerts if limits are under-utilized.

        AGT-001 bugfix. `potential_saving` used to be `gap * 0.30` or
        `limit * 0.20` — a flat assumed marginal rate applied regardless of
        the user's actual income. That is wrong wherever the deduction
        crosses a rebate or surcharge boundary (exactly where it matters
        most — see `calculate_deduction_benefit`'s own docstring for the
        ₹2.1L NPS case where a flat-rate guess is off by ₹47,400), and for a
        user with no taxable income above the basic exemption it overstates
        a real benefit of ₹0 as tens of thousands of rupees. Every alert now
        carries the true benefit from `TaxCalculationEngine.calculate_deduction_benefit`
        (recomputes tax before/after via backend.core), or none at all if
        `current_taxable_income` was not supplied — never a guess.
        """
        try:
            from backend.tools.calculation import TaxCalculationEngine

            def real_benefit(gap: float) -> float | None:
                if current_taxable_income <= 0 or gap <= 0:
                    return None
                benefit = TaxCalculationEngine.calculate_deduction_benefit(
                    deduction_amount=gap,
                    current_taxable_income=current_taxable_income,
                    fy=fy, regime="old", age=age,
                )
                return float(benefit["tax_savings"])

            alerts = []

            # 80C Check (Limit: 1,50,000)
            total_80c = sum([
                investments.get("elss", 0.0),
                investments.get("ppf", 0.0),
                deductions.get("80c", 0.0),
                deductions.get("life_insurance", 0.0)
            ])
            limit_80c = 150000.0
            if total_80c < limit_80c:
                gap = limit_80c - total_80c
                alerts.append({
                    "section": "80C",
                    "title": "Section 80C Limit Underutilized",
                    "severity": "medium" if gap < 50000 else "high",
                    "message": f"You have utilized ₹{total_80c:,.0f} out of ₹{limit_80c:,.0f} under Section 80C. You can invest an additional ₹{gap:,.0f} in ELSS or PPF.",
                    "potential_saving": real_benefit(gap)
                })

            # 80D Check (Health Insurance Premium, limit depends on parents etc., let's mock 25000/50000)
            health_premium = deductions.get("80d", 0.0) or deductions.get("health_insurance", 0.0) or 0.0
            limit_80d = 25000.0
            if health_premium == 0:
                alerts.append({
                    "section": "80D",
                    "title": "No Section 80D Claims Found",
                    "severity": "low",
                    "message": "You haven't claimed any tax benefits for health insurance premium under Section 80D. Premium paid for self, spouse, or children is deductible up to ₹25,000.",
                    "potential_saving": real_benefit(limit_80d)
                })

            # NPS Check (80CCD(1B) additional limit of 50000)
            nps_contrib = investments.get("nps", 0.0) or deductions.get("80ccd", 0.0) or 0.0
            limit_nps = 50000.0
            if nps_contrib < limit_nps:
                gap = limit_nps - nps_contrib
                alerts.append({
                    "section": "80CCD(1B)",
                    "title": "Section 80CCD(1B) NPS Contribution Option",
                    "severity": "low",
                    "message": f"You can claim an additional deduction up to ₹{limit_nps:,.0f} for National Pension Scheme (NPS) contributions. You currently claim ₹{nps_contrib:,.0f}.",
                    "potential_saving": real_benefit(gap)
                })

            return {
                "success": True,
                "alerts": alerts,
                "count": len(alerts),
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            logger.error(f"Error generating tax alerts: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def check_upcoming_deadlines() -> dict[str, Any]:
        """
        Check and calculate days remaining for important tax deadlines.
        """
        try:
            current_date = datetime.now()
            deadlines = [
                {
                    "event": "Q1 Advance Tax Payment Due Date",
                    "date": datetime(current_date.year, 6, 15),
                    "description": "Filing first installment (15%) of advance tax"
                },
                {
                    "event": "ITR Filing Deadline (Individual)",
                    "date": datetime(current_date.year, 7, 31),
                    "description": "Deadline to file Income Tax Return for previous FY"
                },
                {
                    "event": "Q2 Advance Tax Payment Due Date",
                    "date": datetime(current_date.year, 9, 15),
                    "description": "Filing second installment (45%) of advance tax"
                },
                {
                    "event": "Q3 Advance Tax Payment Due Date",
                    "date": datetime(current_date.year, 12, 15),
                    "description": "Filing third installment (75%) of advance tax"
                },
                {
                    "event": "Q4 Advance Tax Payment Due Date",
                    "date": datetime(current_date.year, 3, 15),
                    "description": "Filing final installment (100%) of advance tax"
                }
            ]

            # Correct years for deadlines
            updated_deadlines = []
            for d in deadlines:
                target_year = current_date.year
                if d["event"] == "Q4 Advance Tax Payment Due Date" and current_date.month > 3:
                    target_year += 1

                target_date = d["date"].replace(year=target_year)
                days_left = (target_date - current_date).days

                # If deadline has passed for this year, bump to next year
                if days_left < 0:
                    target_date = target_date.replace(year=target_date.year + 1)
                    days_left = (target_date - current_date).days

                updated_deadlines.append({
                    "event": d["event"],
                    "due_date": target_date.date().isoformat(),
                    "description": d["description"],
                    "days_remaining": days_left,
                    "status": "critical" if days_left <= 7 else ("warning" if days_left <= 30 else "normal")
                })

            return {
                "success": True,
                "deadlines": sorted(updated_deadlines, key=lambda x: x["days_remaining"]),
                "last_checked": current_date.isoformat()
            }
        except Exception as e:
            logger.error(f"Error checking deadlines: {e}")
            return {"success": False, "error": str(e)}
