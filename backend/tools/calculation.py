"""
Tax calculation tools — a thin adapter over `backend.core`.

DEM-006 — what was deleted and why
-----------------------------------
This module used to hold its own `TAX_SLABS` and `DEDUCTION_LIMITS` tables and
compute tax directly. It was one of SEVEN places in the codebase carrying tax
constants, and they disagreed with each other:

    standard deduction   50,000 here · 50,000 in india_tax_data_fetcher
                         75,000 in data_validator · absent from the engine
    slabs                FY 2023-24 vintage in three files, FY 2020-21 in a
                         fourth, FY 2024-25 in a fifth
    80D                  a flat 1,50,000, a figure that appears nowhere in the
                         section
    LTCG                 a flat 20% "ignoring indexation", with no exemption

None of that lives here now. Every figure comes from `backend.core`, which
reads versioned rule packs and is covered by 347 tests including boundary cases
at every threshold.

This file is an ADAPTER: it converts loose dict-shaped tool arguments into the
core's typed inputs and converts results back. It contains no tax knowledge,
and the import-linter contract stops it acquiring any.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from backend.core.provenance.money import ZERO, Money
from backend.core.rules import RuleError, fy_for_date, load_ruleset
from backend.core.tax_engine import (
    AssetClass,
    DeductionClaim,
    Disposal,
    TaxInput,
    compute_80ccd2,
    compute_80cce_group,
    compute_80d,
    compute_capital_gains,
    compute_hra_exemption,
    compute_tax,
)

logger = logging.getLogger(__name__)


def _money(value: Any) -> Money:
    """Coerce a loose tool argument into Money.

    Callers upstream still hand us floats. They are converted through `str` so
    the decimal the caller wrote is preserved exactly; the core itself never
    sees a float.
    """
    if value is None:
        return ZERO
    if isinstance(value, float):
        return Money(str(value))
    return Money(value)


def current_fy(today: date | None = None) -> str:
    """Resolve the financial year for a date.

    Callers must still pass `fy` explicitly wherever a specific year is meant —
    this is only for "as of today". The core has no default year, deliberately.
    """
    return fy_for_date(today or date.today())


class TaxCalculationEngine:
    """Adapter retained under its original name so existing tool wiring keeps
    working. All computation is delegated."""

    @staticmethod
    def calculate_income_tax(
        taxable_income: float,
        fy: str | None = None,
        regime: str = "new",
        age: int = 0,
        **_ignored: Any,
    ) -> dict[str, Any]:
        fy = fy or current_fy()
        result = compute_tax(
            TaxInput(fy=fy, regime=regime, age=age, other_sources=_money(taxable_income))
        )
        return {
            "fy": fy,
            "regime": regime,
            "income_tax": result.tax_on_slabs.to_json(),
            "rebate_87a": result.rebate_87a.to_json(),
            "surcharge": result.surcharge.to_json(),
            "cess": result.cess.to_json(),
            "total_tax": result.total_tax.to_json(),
            "total_tax_rounded": result.total_tax_rounded.to_json(),
            "effective_rate": result.effective_rate,
            "marginal_rate": result.marginal_rate,
            "worksheet": result.trace.render(),
            "trace": result.trace.to_dict(),
            "confidence": result.confidence.to_dict(),
        }

    @staticmethod
    def calculate_tax_with_deductions(
        gross_income: float,
        deductions: dict[str, float] | None = None,
        fy: str | None = None,
        regime: str = "new",
        age: int = 0,
        is_salary: bool = True,
        **_ignored: Any,
    ) -> dict[str, Any]:
        fy = fy or current_fy()
        income = _money(gross_income)
        result = compute_tax(
            TaxInput(
                fy=fy,
                regime=regime,
                age=age,
                salary=income if is_salary else ZERO,
                other_sources=ZERO if is_salary else income,
                deductions={k: _money(v) for k, v in (deductions or {}).items()},
            )
        )
        return {
            "fy": fy,
            "regime": regime,
            "gross_income": result.gross_total_income.to_json(),
            "total_deductions": result.total_deductions.to_json(),
            "taxable_income": result.taxable_income.to_json(),
            "total_tax": result.total_tax.to_json(),
            "total_tax_rounded": result.total_tax_rounded.to_json(),
            "effective_rate": result.effective_rate,
            "worksheet": result.trace.render(),
            "trace": result.trace.to_dict(),
            "confidence": result.confidence.to_dict(),
        }

    @staticmethod
    def compare_regimes(
        gross_income: float,
        deductions: dict[str, float] | None = None,
        fy: str | None = None,
        age: int = 0,
        is_salary: bool = True,
    ) -> dict[str, Any]:
        """Old versus new on the same facts.

        Both sides come from one engine and one rule pack, so the comparison is
        internally consistent. v1 computed the two regimes in a different module
        with FY 2024-25 slabs and a hard rebate cliff at ₹7,00,001.
        """
        fy = fy or current_fy()
        income = _money(gross_income)
        claims = {k: _money(v) for k, v in (deductions or {}).items()}

        outcomes = {}
        for regime in ("old", "new"):
            r = compute_tax(
                TaxInput(
                    fy=fy,
                    regime=regime,
                    age=age,
                    salary=income if is_salary else ZERO,
                    other_sources=ZERO if is_salary else income,
                    deductions=claims,
                )
            )
            outcomes[regime] = r

        better = min(outcomes, key=lambda k: outcomes[k].total_tax)
        saving = (
            outcomes["old" if better == "new" else "new"].total_tax
            - outcomes[better].total_tax
        )
        return {
            "fy": fy,
            "old": {
                "taxable_income": outcomes["old"].taxable_income.to_json(),
                "total_tax": outcomes["old"].total_tax.to_json(),
            },
            "new": {
                "taxable_income": outcomes["new"].taxable_income.to_json(),
                "total_tax": outcomes["new"].total_tax.to_json(),
            },
            "better_regime": better,
            "saving": saving.to_json(),
            "worksheet_old": outcomes["old"].trace.render(),
            "worksheet_new": outcomes["new"].trace.render(),
        }

    @staticmethod
    def calculate_deduction_benefit(
        deduction_amount: float,
        current_taxable_income: float,
        fy: str | None = None,
        regime: str = "old",
        age: int = 0,
    ) -> dict[str, Any]:
        """What a deduction is actually worth, by recomputing both ways.

        Never `amount × marginal_rate`: that estimate is wrong wherever the
        deduction crosses a rebate or surcharge boundary, which is exactly where
        it matters most. The ₹2.1L employer-NPS case moves a taxpayer from
        ₹97,500 to ₹15,600 — a marginal-rate estimate would have said ₹63,000.
        """
        fy = fy or current_fy()
        base = _money(current_taxable_income)
        amount = _money(deduction_amount)

        before = compute_tax(TaxInput(fy=fy, regime=regime, age=age, other_sources=base))
        after = compute_tax(
            TaxInput(
                fy=fy, regime=regime, age=age,
                other_sources=(base - amount).clamp_non_negative(),
            )
        )
        saving = (before.total_tax - after.total_tax).clamp_non_negative()
        return {
            "fy": fy,
            "deduction_amount": amount.to_json(),
            "tax_before": before.total_tax.to_json(),
            "tax_after": after.total_tax.to_json(),
            "tax_savings": saving.to_json(),
            "effective_benefit_rate": (
                f"{(saving.amount / amount.amount * 100):.2f}%" if amount > ZERO else "0.00%"
            ),
        }

    @staticmethod
    def calculate_hra_exemption(
        basic_salary: float,
        hra_received: float,
        rent_paid: float,
        is_metro: bool = False,
        fy: str | None = None,
    ) -> dict[str, Any]:
        rs = load_ruleset(fy or current_fy())
        out = compute_hra_exemption(
            _money(basic_salary), _money(hra_received), _money(rent_paid), is_metro, rs
        )
        return {
            "exempt_hra": out.allowed.to_json(),
            "taxable_hra": out.disallowed.to_json(),
            "notes": out.notes,
            "worksheet": [s.label for s in out.steps],
        }

    @staticmethod
    def calculate_80d(
        self_premium: float,
        parents_premium: float = 0,
        self_is_senior: bool = False,
        parents_are_senior: bool = False,
        preventive_checkup: float = 0,
        fy: str | None = None,
    ) -> dict[str, Any]:
        rs = load_ruleset(fy or current_fy())
        out = compute_80d(
            DeductionClaim(
                "80D",
                _money(self_premium),
                self_is_senior=self_is_senior,
                parents_are_senior=parents_are_senior,
                parents_premium=_money(parents_premium),
                preventive_checkup=_money(preventive_checkup),
            ),
            rs,
        )
        return {
            "allowed": out.allowed.to_json(),
            "claimed": out.claimed.to_json(),
            "disallowed": out.disallowed.to_json(),
            "notes": out.notes,
        }

    @staticmethod
    def calculate_80c_group(
        claims: dict[str, float],
        fy: str | None = None,
    ) -> dict[str, Any]:
        rs = load_ruleset(fy or current_fy())
        out = compute_80cce_group({k: _money(v) for k, v in claims.items()}, rs)
        return {
            "allowed": out.allowed.to_json(),
            "claimed": out.claimed.to_json(),
            "disallowed": out.disallowed.to_json(),
            "notes": out.notes,
        }

    @staticmethod
    def calculate_employer_nps(
        employer_contribution: float,
        salary: float,
        regime: str = "new",
        is_government_employee: bool = False,
        fy: str | None = None,
    ) -> dict[str, Any]:
        rs = load_ruleset(fy or current_fy())
        out = compute_80ccd2(
            _money(employer_contribution), _money(salary), rs, regime,
            is_government_employee=is_government_employee,
        )
        return {"allowed": out.allowed.to_json(), "claimed": out.claimed.to_json()}


class CapitalGainsTaxCalculator:
    """Adapter over the core capital gains engine."""

    @staticmethod
    def calculate(
        disposals: list[dict[str, Any]],
        fy: str | None = None,
        resident_individual: bool = True,
    ) -> dict[str, Any]:
        rs = load_ruleset(fy or current_fy())
        parsed = [
            Disposal(
                asset=AssetClass(d.get("asset", "other")),
                acquired_on=date.fromisoformat(str(d["acquired_on"])),
                sold_on=date.fromisoformat(str(d["sold_on"])),
                cost=_money(d.get("cost")),
                consideration=_money(d.get("consideration")),
                improvement_cost=_money(d.get("improvement_cost")),
                transfer_expenses=_money(d.get("transfer_expenses")),
                fmv_2018_01_31=(
                    _money(d["fmv_2018_01_31"]) if d.get("fmv_2018_01_31") else None
                ),
                description=d.get("description", ""),
            )
            for d in disposals
        ]

        try:
            r = compute_capital_gains(parsed, rs, resident_individual=resident_individual)
        except RuleError as exc:
            # The split-year refusal. Better an explicit failure than
            # post-reform rates silently applied to a pre-reform transfer.
            return {"success": False, "error": str(exc)}

        return {
            "success": True,
            "fy": rs.fy,
            "equity_ltcg_gross": r.equity_ltcg_gross.to_json(),
            "equity_ltcg_exemption": r.equity_ltcg_exemption.to_json(),
            "equity_ltcg_taxable": r.equity_ltcg_taxable.to_json(),
            "equity_stcg": r.equity_stcg.to_json(),
            "other_ltcg": r.other_ltcg.to_json(),
            "slab_taxed_gains": r.slab_taxed_gains.to_json(),
            "total_tax": r.total_tax.to_json(),
            "special_rate_income": r.total_special_rate_income.to_json(),
            "notes": r.notes,
            "worksheet": r.trace.render(),
        }
