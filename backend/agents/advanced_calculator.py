"""
Step 9.3: Advanced Calculator Agent
===================================

Complex tax calculations with multiple income sources.
India-specific tax rules + database persistence.
"""

import logging
import time
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

try:
    from backend.db.orm_models_step9_10 import TaxCalculation
except ImportError:
    from backend.db.orm_models import TaxCalculation
from backend.agents.base_agent import AgentOutput, TaxAgent, confidence_score, derive_confidence
from backend.services.india_tax_data_fetcher import india_tax_data
from backend.tools.calculation import TaxCalculationEngine, current_fy

logger = logging.getLogger(__name__)


class AdvancedCalculatorAgent(TaxAgent):
    """
    Handle complex tax calculations.
    
    • Multiple income sources
    • Capital gains (STCG/LTCG)
    • Loss carry forward & set-off
    • GST impact calculation
    • Advance tax computation
    • Tax optimization
    • Save to database
    """

    def __init__(self, db: Session = None):
        super().__init__("advanced_calculator_agent", "tax_calculation")
        self.db = db

    def set_db(self, db: Session):
        """Set database session."""
        self.db = db
        return self

    async def execute(
        self,
        user_query: str,
        user_context: dict[str, Any],
        tools=None,
        **kwargs
    ) -> AgentOutput:
        """
        Calculate complex tax scenarios.
        
        Workflow:
          1. Gather all income sources
          2. Calculate each income type tax
          3. Apply capital gains rules
          4. Apply loss set-off rules
          5. Calculate deductions
          6. Compute final tax liability
          7. Suggest optimizations
          8. Save to database
        """
        start_time = time.time()

        if tools is not None:
            self.set_tools(tools)

        try:
            self.logger.info(f"Running advanced calculation for user {user_context.get('user_id')}")

            user_id = user_context.get("user_id")

            # STEP 0: FY, regime, age — from the real rule-pack loader, not
            # IndiaTaxDataFetcher (stale, DEM-006). Still used below for
            # `deduction_limits` in _suggest_optimizations and for GST, which
            # this pass does not touch.
            tax_data = await india_tax_data.get_current_tax_data()
            fy = current_fy()
            regime = user_context.get("tax_regime", "new")
            age = int(user_context.get("age", 0) or 0)

            # STEP 1: Gather income data
            if self.tools:
                income_data = await self.call_tool(
                    "get_user_income_history",
                    user_id=user_id,
                    years=1
                )
                incomes = income_data.get("result", {}).get("income_history", [{}])[0] if income_data.get("result") else {}
            else:
                incomes = user_context

            # Extract income sources
            salary = float(incomes.get("salary_income", user_context.get("annual_income", 0) or 0))
            business = float(incomes.get("business_income", 0))
            rental = float(incomes.get("rental_income", 0))
            ltcg = float(user_context.get("long_term_gains", 0) or incomes.get("long_term_gains", 0) or 0)
            stcg = float(user_context.get("short_term_gains", 0) or incomes.get("short_term_gains", 0) or 0)
            other_income = float(incomes.get("other_income", 0))

            # s.24(a): flat 30% standard deduction against rental (house
            # property) income — statutory, not elective, and separate from
            # the s.24(b) home loan interest deduction claimed below. The
            # previous 20% figure had no statutory basis.
            rental_after_std_deduction = max(0.0, rental * 0.70)

            gross_income = salary + business + rental + ltcg + stcg + other_income

            # STEP 2: Get deductions, mapped to real section codes and
            # capped to real per-section limits (fixed in get_user_deductions
            # — it used to return raw uncapped sums under labels like "NPS"
            # and "Sec24b" that this engine does not recognise).
            if self.tools:
                deductions_data = await self.call_tool(
                    "get_user_deductions",
                    user_id=user_id
                )
                deductions_dict = deductions_data.get("result", {}).get("deductions", {})
            else:
                deductions_dict = user_context.get("deductions", {})

            deductions_for_engine = self._deductions_for_engine(deductions_dict)
            total_claimed_deductions = sum(deductions_for_engine.values())

            # STEP 3: Capital gains at special (non-slab) rates. Only
            # aggregate STCG/LTCG totals are available here — no per-asset
            # acquisition data — so this assumes equity (111A/112A), the
            # common case, rather than running the disposal-based engine
            # `CapitalGainsTaxCalculator` needs and can't be fed from this
            # agent's inputs.
            cg_rates = TaxCalculationEngine.equity_capital_gains_rates(fy)
            ltcg_exemption = float(cg_rates["ltcg_annual_exemption"])
            ltcg_rate = float(cg_rates["ltcg_rate"])
            stcg_rate = float(cg_rates["stcg_rate"])
            ltcg_taxable = max(0.0, ltcg - ltcg_exemption)
            ltcg_tax = ltcg_taxable * ltcg_rate
            stcg_tax = stcg * stcg_rate
            special_rate_income = ltcg_taxable + stcg
            special_rate_tax = ltcg_tax + stcg_tax

            # STEP 4: The real computation — one combined progressive
            # calculation across all income heads, with real deductions,
            # the real FY's slabs, and the s.87A marginal-relief rebate.
            # This replaces per-component slab tax summed afterward, which
            # is wrong for progressive brackets (each component re-used the
            # 0%/5% bands from ₹0 rather than the whole being taxed once).
            tax_result = TaxCalculationEngine.calculate_tax_full(
                salary=salary,
                house_property=rental_after_std_deduction,
                business=business,
                other_sources=other_income,
                deductions=deductions_for_engine,
                fy=fy,
                regime=regime,
                age=age,
                special_rate_income=special_rate_income,
                special_rate_tax=special_rate_tax,
            )

            taxable_income = float(tax_result["taxable_income"])
            final_tax = float(tax_result["income_tax"]) + special_rate_tax
            surcharge = float(tax_result["surcharge"])
            cess = float(tax_result["cess"])
            total_tax_liability = float(tax_result["total_tax_liability"])
            effective_rate = float(tax_result["effective_rate"].rstrip("%")) if isinstance(tax_result["effective_rate"], str) else float(tax_result["effective_rate"])

            # STEP 5: Apply loss set-off rules, against the actual gain/
            # income amounts — not, as before, against the TAX on them.
            losses = user_context.get("losses", {})
            loss_setoff = self._apply_loss_setoff(
                losses,
                {
                    "capital_gains": ltcg + stcg,
                    "other_income": salary + rental,
                },
            )

            # STEP 6: Calculate GST impact (if applicable)
            gst_impact = self._calculate_gst_impact(user_context, business)

            # STEP 7: Optimization suggestions
            optimization = self._suggest_optimizations(
                gross_income,
                deductions_for_engine.get("80C", 0.0),
                total_tax_liability,
                user_context,
                tax_data,
                taxable_income,
                fy=fy,
            )

            # STEP 8: Calculate TDS & refund/balance
            tds_paid = float(user_context.get("tds_paid", 0))
            refund = max(0, tds_paid - total_tax_liability)
            balance_due = max(0, total_tax_liability - tds_paid)

            result = {
                "financial_year": fy,
                "assessment_year": tax_data.get("assessment_year"),

                "gross_income": gross_income,
                "income_breakdown": {
                    "salary": salary,
                    "business": business,
                    "rental": rental,
                    "capital_gains_stcg": stcg,
                    "capital_gains_ltcg": ltcg,
                    "other_income": other_income
                },

                "deductions": {
                    "total_claimed": total_claimed_deductions,
                    "claimed": total_claimed_deductions,  # For backward compatibility with existing tests
                    "details": self._format_deductions(deductions_dict)
                },

                "taxable_income": taxable_income,

                "tax_calculation": {
                    "income_tax": final_tax,
                    "surcharge": surcharge,
                    "cess": cess,
                    "total_tax_liability": total_tax_liability
                },

                "tax_breakdown": {  # For backward compatibility with existing tests
                    "income_tax": final_tax,
                    "surcharge": surcharge,
                    "cess": cess
                },
                "total_tax_liability": total_tax_liability,  # For backward compatibility with existing tests

                "tax_rates": {
                    "income_tax_rate": tax_result["marginal_rate"],
                    "surcharge_rate": f"{(surcharge / final_tax * 100):.0f}%" if final_tax > 0 else "0%",
                    "cess_rate": "4%"
                },

                "effective_tax_rate": round(effective_rate, 2),

                "loss_setoff": loss_setoff,
                "loss_setoff_details": loss_setoff,  # For backward compatibility with existing tests

                "gst_details": gst_impact,

                "tds_credit": {
                    "tds_paid": tds_paid,
                    "advance_tax_paid": float(user_context.get("advance_tax_paid", 0)),
                    "total_credit": tds_paid + float(user_context.get("advance_tax_paid", 0))
                },

                "refund_or_balance": {
                    "estimated_refund": refund,
                    "balance_due": balance_due,
                    "status": f"REFUND ₹{refund:,.0f}" if refund > 0 else (f"PAY ₹{balance_due:,.0f}" if balance_due > 0 else "NO REFUND/TAX"),
                    "notes": [
                        "Refund will be credited within 2-4 weeks",
                        "Balance to be paid before ITR filing deadline",
                        "Amount is estimated, actual may vary"
                    ]
                },

                "optimization_suggestions": optimization,
                "potential_savings": sum(s.get("savings") or 0 for s in optimization),

                "summary": {
                    "total_income": await india_tax_data.format_currency(gross_income),
                    "total_deductions": await india_tax_data.format_currency(total_claimed_deductions),
                    "taxable_income": await india_tax_data.format_currency(taxable_income),
                    "total_tax": await india_tax_data.format_currency(total_tax_liability),
                    "effective_rate": f"{effective_rate:.2f}%"
                }
            }

            # STEP 13: Save to database
            db_session = self.db
            if not db_session:
                try:
                    from backend.orchestrator.graph import db_session_var
                    db_session = db_session_var.get()
                except Exception:
                    db_session = None

            if db_session and user_id:
                await self._save_to_database(user_id, result, db_session)

            execution_time = (time.time() - start_time) * 1000

            return self._create_output(
                result=result,
                status="success",
                confidence=confidence_score(derive_confidence()),
                reasoning="Advanced tax calculation completed including multiple income heads and capital gains.",
                execution_time_ms=execution_time
            )

        except Exception as e:
            self.logger.error(f"Error in advanced calculator: {e}", exc_info=True)
            execution_time = (time.time() - start_time) * 1000

            return self._create_output(
                result={"error": str(e)},
                status="error",
                confidence=0.0,  # execution failed — not a score
                reasoning=f"Error running complex calculations: {e!s}",
                execution_time_ms=execution_time
            )

    def _deductions_for_engine(self, deductions_dict: dict[str, Any]) -> dict[str, float]:
        """Flatten `get_user_deductions`'s per-section shape into the plain
        {code: amount} dict `TaxCalculationEngine.calculate_tax_full` needs.

        Section codes come from the caller already capped to their real
        statutory limits (see `get_user_deductions`) — this does no capping
        of its own, only extraction, so it stays correct if a caller's caps
        change rather than silently re-applying a second, possibly stale set.
        """
        if not deductions_dict or not isinstance(deductions_dict, dict):
            return {}

        flat: dict[str, float] = {}
        for code, deduction in deductions_dict.items():
            if isinstance(deduction, dict):
                flat[code] = float(deduction.get("claimed", deduction.get("amount", 0)) or 0)
            else:
                flat[code] = float(deduction or 0)
        return flat

    def _apply_loss_setoff(
        self,
        losses: dict[str, float],
        income_amounts: dict[str, float]
    ) -> dict[str, Any]:
        """
        Apply loss set-off rules (India-specific).

        Rules:
        • Business loss can offset any income
        • Capital loss can only offset capital gains

        `income_amounts` carries the actual gain/income figures being offset
        against (`capital_gains`, `other_income`) — previously this was
        fed the TAX on those amounts instead of the amounts themselves,
        which set losses off against a number roughly 1/5th to 1/3rd the
        size of what the law actually allows.
        """
        business_loss = losses.get("business", 0)
        capital_loss = losses.get("capital", 0)

        # Capital loss set-off (only against capital gains)
        capital_gains = income_amounts.get("capital_gains", 0)
        capital_loss_utilized = min(capital_loss, capital_gains)
        capital_loss_carried = max(0, capital_loss - capital_gains)

        # Business loss set-off
        other_income = income_amounts.get("other_income", 0)
        business_loss_utilized = min(business_loss, other_income)
        business_loss_carried = max(0, business_loss - other_income)

        return {
            "business_loss_used": business_loss_utilized,
            "business_loss_carried_forward": business_loss_carried,
            "capital_loss_used": capital_loss_utilized,
            "capital_loss_carried_forward": capital_loss_carried,
            "carryforward_limit": "Business: 8 years | Capital: Indefinite",
            "note": "Can carry forward unused losses to next year"
        }

    def _calculate_gst_impact(
        self,
        user_context: dict[str, Any],
        business_income: float
    ) -> dict[str, Any]:
        """Calculate GST impact if applicable."""
        gst_data = {}

        turnover = business_income + user_context.get("turnover", 0)

        if turnover > 4000000:  # ₹40 lakh threshold
            gst_data = {
                "gst_applicable": True,
                "threshold": 4000000,
                "turnover": turnover,
                "registration_required": True,
                "gst_to_pay": turnover * 0.18,  # Assume 18% GST
                "gst_refund_potential": turnover * 0.18 * 0.3,  # Estimated ITC
                "net_gst_liability": turnover * 0.18 * 0.7,
                "filing_requirement": "Monthly GSTR-1, Quarterly GSTR-3B",
                "action": "Register on GST portal if not done"
            }
        else:
            gst_data = {
                "gst_applicable": False,
                "threshold": 4000000,
                "turnover": turnover,
                "registration_required": False,
                "message": "Below GST threshold - registration optional"
            }

        return gst_data

    def _format_deductions(self, deductions_dict: dict[str, Any]) -> list[dict[str, Any]]:
        """Format deductions for display."""
        deduction_list = []

        if isinstance(deductions_dict, dict):
            for code, details in deductions_dict.items():
                if isinstance(details, dict):
                    deduction_list.append({
                        "code": code,
                        "name": details.get("name", code),
                        "amount": details.get("amount", details.get("claimed", 0)),
                        "limit": details.get("limit", "No limit")
                    })
                else:
                    deduction_list.append({
                        "code": code,
                        "name": code,
                        "amount": float(details),
                        "limit": "No limit"
                    })

        return deduction_list[:10]  # Top 10

    def _suggest_optimizations(
        self,
        gross_income: float,
        current_deductions: float,
        tax_liability: float,
        user_context: dict[str, Any],
        tax_data: dict[str, Any],
        taxable_income: float = 0.0,
        fy: str | None = None,
    ) -> list[dict[str, Any]]:
        """Suggest tax optimization strategies (India-specific).

        AGT-001 bugfix. Every suggestion here used to carry a fabricated
        figure: a flat `headroom * 0.20` (wrong wherever a rebate or
        surcharge boundary is crossed — the exact case
        `calculate_deduction_benefit`'s docstring names), or a flat-out
        hardcoded guess (80D was "₹30,000 savings, ₹150,000 max limit" —
        150,000 is 80C's limit, not 80D's, which is ₹25,000). Every figure
        below is now `TaxCalculationEngine.calculate_deduction_benefit`'s
        real before/after recomputation. `fy` is now the real current FY
        from `backend.core.rules` (the caller's base calculation was fixed
        alongside this to stop using `IndiaTaxDataFetcher`'s stale data) —
        `deduction_limits` below still comes from `tax_data`
        (IndiaTaxDataFetcher) for the 80C headroom figure, which is the one
        limit in that source that hasn't actually changed across recent FYs;
        the 80D limit next to it is intentionally NOT read from the same
        source, for the reason noted there.
        """
        fy = fy or current_fy()
        base_income = taxable_income

        def benefit(amount: float) -> float:
            if amount <= 0 or base_income <= 0:
                return 0.0
            result = TaxCalculationEngine.calculate_deduction_benefit(
                deduction_amount=amount, current_taxable_income=base_income,
                fy=fy, regime="old",
            )
            return float(result["tax_savings"])

        suggestions = []
        deduction_limits = tax_data["deduction_limits"]

        # Suggestion 1: Maximize 80C. `current_deductions` is specifically
        # the 80C claim (see the `_deductions_for_engine(...).get("80C")`
        # call site) — it used to be the grand total across ALL sections,
        # which meant maxing out 80D/24b/80E alone (with zero 80C) could
        # read as "80C already maxed" and suppress this suggestion entirely.
        deduction_80c_limit = deduction_limits["80C"]["limit"]
        if current_deductions < deduction_80c_limit:
            headroom = deduction_80c_limit - current_deductions
            tax_savings = benefit(headroom)
            suggestions.append({
                "strategy": "Maximize 80C (Life Insurance, ELSS, PPF, NSC)",
                "headroom": headroom,
                "potential_savings": tax_savings,
                "savings": tax_savings,
                "difficulty": "Easy",
                "action": f"Invest additional ₹{headroom:,.0f} before March 31"
            })

        # Suggestion 2: Health Insurance (80D)
        if not user_context.get("has_health_insurance") and not user_context.get("health_insurance"):
            # Not read from deduction_limits: IndiaTaxDataFetcher's own
            # dataset has "80D": {"limit": 150000} — that is 80C's limit,
            # copy-pasted. ₹25,000 (₹50,000 for a senior-citizen premium) is
            # the actual s.80D general limit; hardcoded here as a stopgap,
            # not read from core/rules — a separate, larger finding
            # (IndiaTaxDataFetcher needs replacing with a real rule-pack
            # reader per docs/IMPLEMENTATION_PLAN.md's RuleSetProvider).
            limit_80d = 25000
            tax_savings = benefit(limit_80d)
            suggestions.append({
                "strategy": "Get health insurance (80D deduction)",
                "potential_savings": tax_savings,
                "savings": tax_savings,
                "difficulty": "Easy",
                "action": f"Buy health insurance policy (₹{limit_80d:,.0f} max limit)"
            })

        # Suggestion 3: NPS Contribution (80CCD(1B))
        if gross_income > 500000:
            # Same issue: IndiaTaxDataFetcher's "80CCD": {"limit": 150000} is
            # wrong for the additional voluntary contribution this suggestion
            # means — ₹50,000 is the real s.80CCD(1B) limit.
            limit_nps = 50000
            tax_savings = benefit(limit_nps)
            suggestions.append({
                "strategy": "Contribute to NPS (Additional 80CCD)",
                "potential_savings": tax_savings,
                "savings": tax_savings,
                "difficulty": "Medium",
                "action": f"Open NPS account and invest ₹{limit_nps:,.0f}"
            })

        # Suggestion 4: Education Loan (80E) — no statutory cap, the real
        # interest paid is itself the deduction amount, so this one number
        # (unlike the others) was already a real user-stated figure. Only the
        # *0.20 conversion to a savings estimate was fabricated.
        education_loan_interest = user_context.get("education_loan", 0)
        if education_loan_interest > 0:
            tax_savings = benefit(education_loan_interest)
            suggestions.append({
                "strategy": "Claim education loan interest (80E)",
                "potential_savings": tax_savings,
                "savings": tax_savings,
                "difficulty": "Easy",
                "action": "Claim interest paid on education loan"
            })

        # Suggestion 5: Loss Carry Forward. Losses reduce taxable capital
        # gains/business income directly; they are not a Chapter VI-A
        # deduction against total income, so `calculate_deduction_benefit`
        # (which models exactly that) does not apply here, and neither did
        # the *0.20 it replaces. No rupee figure is asserted — advising a
        # user to route this to a CA is the honest answer, not a guess in
        # either direction.
        losses = user_context.get("losses", {})
        if losses.get("capital", 0) > 0 or losses.get("business", 0) > 0:
            suggestions.append({
                "strategy": "Use loss carry forward wisely",
                "potential_savings": None,
                "savings": None,
                "difficulty": "Hard",
                "action": "Consult CA for optimal loss set-off strategy"
            })

        return suggestions

    async def _save_to_database(self, user_id: str, result: dict[str, Any], db_session):
        """Save tax calculation to database."""
        try:
            tax_calc = TaxCalculation(
                user_id=user_id,
                financial_year=result["financial_year"],
                income_sources=result["income_breakdown"],
                deductions=result.get("deductions"),
                capital_gains={"stcg": result["income_breakdown"]["capital_gains_stcg"],
                              "ltcg": result["income_breakdown"]["capital_gains_ltcg"]},
                losses=None,
                gross_income=Decimal(str(result["gross_income"])),
                taxable_income=Decimal(str(result["taxable_income"])),
                income_tax=Decimal(str(result["tax_calculation"]["income_tax"])),
                surcharge=Decimal(str(result["tax_calculation"]["surcharge"])),
                cess=Decimal(str(result["tax_calculation"]["cess"])),
                total_tax_liability=Decimal(str(result["tax_calculation"]["total_tax_liability"])),
                effective_rate=Decimal(str(result["effective_tax_rate"])),
                optimization_suggestions=result.get("optimization_suggestions")
            )

            db_session.add(tax_calc)

            if isinstance(db_session, AsyncSession):
                await db_session.commit()
            else:
                db_session.commit()
            self.logger.info(f"Tax calculation saved for user {user_id}")

        except Exception as e:
            self.logger.error(f"Error saving to database: {e}")
            try:
                if isinstance(db_session, AsyncSession):
                    await db_session.rollback()
                else:
                    db_session.rollback()
            except Exception as rollback_err:
                self.logger.error(f"Error rolling back: {rollback_err}")
