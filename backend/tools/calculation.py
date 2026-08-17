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
from decimal import Decimal
from typing import Any

from backend.core.provenance.ledger import ledger_from_trace as _ledger_from_trace
from backend.core.provenance.money import ZERO, Money
from backend.core.provenance.panel import build_panel as _build_panel
from backend.core.rules import RuleError, fy_for_date, load_ruleset
from backend.core.tax_engine import (
    AssetClass,
    DeductionClaim,
    Disposal,
    TaxInput,
    compare_regimes,
    compute_80ccd2,
    compute_80cce_group,
    compute_80d,
    compute_capital_gains,
    compute_hra_exemption,
    compute_tax,
)

# Aliased because the adapter exposes static methods of the same names, and a
# method shadowing the function it delegates to is a recursion waiting to be
# written. `compare_regimes` gets away with it only because the class body is
# not in the method's lookup chain — not a distinction worth relying on twice.
from backend.core.tax_engine import GainBucket as _GainBucket
from backend.core.tax_engine import Position as _Position
from backend.core.tax_engine import build_calendar as _build_calendar
from backend.core.tax_engine import harvest as _harvest
from backend.core.tax_engine import optimise_salary as _optimise_salary
from backend.core.tax_engine import plan_advance_tax as _plan_advance_tax
from backend.core.tax_engine import refund_interest as _refund_interest
from backend.core.tax_engine import select_itr_form as _select_itr_form
from backend.core.tax_engine import set_off_losses as _set_off_losses
from backend.core.tax_engine.deadlines import TaxpayerProfile as _TaxpayerProfile
from backend.core.tax_engine.itr_form import EntityType as _EntityType
from backend.core.tax_engine.itr_form import FilerProfile as _FilerProfile
from backend.core.tax_engine.itr_form import Residency as _Residency
from backend.core.tax_engine.salary_structure import SalaryStructure as _SalaryStructure

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
            "effective_rate": result.effective_rate,
            "marginal_rate": result.marginal_rate,
            "worksheet": result.trace.render(),
            "trace": result.trace.to_dict(),
            "confidence": result.confidence.to_dict(),
            # PLN-007: one ledger entry per figure, so the UI can make every
            # number click-through rather than rendering bare digits.
            "ledger": _ledger_from_trace(result.trace, fy).to_dict(),
            # EVD-005: the four evidence tabs, assembled from THIS result so
            # they cannot show a worksheet from one run beside a confidence
            # score from another.
            "evidence_panel": _build_panel(result, fy).to_dict(),
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
        """Old versus new on the same facts, plus the exact breakeven.

        Delegates to `backend.core.tax_engine.regime_compare` — this adapter had
        its own copy of the comparison, which is how two implementations drift.
        The core version adds what the agent actually needs to give useful
        advice: the deduction total at which the answer would change, and the
        notes about lock-in and about 80CCD(2) being regime-neutral.
        """
        return compare_regimes(
            _money(gross_income),
            {k: _money(v) for k, v in (deductions or {}).items()},
            fy=fy or current_fy(),
            age=age,
            is_salary=is_salary,
        ).to_dict()

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
    def plan_advance_tax(
        total_tax: float,
        fy: str | None = None,
        taxes_deducted: float = 0,
        payments: dict[str, float] | None = None,
        age: int = 0,
        has_business_income: bool = False,
        is_presumptive: bool = False,
        excused_tax_by_date: dict[str, float] | None = None,
        assessed_on: str | None = None,
    ) -> dict[str, Any]:
        """Instalment schedule and ss.234B/234C interest.

        Dates arrive as ISO strings from the tool layer and are parsed here;
        the core takes real dates, because "15/06/2026" and "06-15" are the
        kind of thing that silently becomes the wrong year.
        """
        return _plan_advance_tax(
            _money(total_tax),
            fy or current_fy(),
            taxes_deducted=_money(taxes_deducted),
            payments={
                date.fromisoformat(k): _money(v) for k, v in (payments or {}).items()
            },
            age=age,
            has_business_income=has_business_income,
            is_presumptive=is_presumptive,
            excused_tax_by_date={
                date.fromisoformat(k): _money(v)
                for k, v in (excused_tax_by_date or {}).items()
            },
            assessed_on=date.fromisoformat(assessed_on) if assessed_on else None,
        ).to_dict()

    @staticmethod
    def refund_interest(
        refund: float,
        fy: str | None = None,
        granted_on: str | None = None,
    ) -> dict[str, Any]:
        """Interest the department owes on a refund, s.244A at 0.5% a month."""
        return _refund_interest(
            _money(refund),
            fy or current_fy(),
            granted_on=date.fromisoformat(granted_on) if granted_on else None,
        ).to_dict()

    @staticmethod
    def set_off_capital_losses(
        gains: dict[str, float],
        fy: str | None = None,
        stcl: float = 0,
        ltcl: float = 0,
        brought_forward_stcl: float = 0,
        brought_forward_ltcl: float = 0,
        marginal_rate: str = "0.30",
    ) -> dict[str, Any]:
        """Allocate capital losses across gain buckets.

        `gains` is keyed by `GainBucket` value — how the gain is TAXED, not what
        the asset is. Two holdings in the same bucket are interchangeable for
        set-off; two in different buckets are not, and that difference is the
        entire point of the feature.
        """
        return _set_off_losses(
            {_GainBucket(k): _money(v) for k, v in gains.items()},
            fy or current_fy(),
            stcl=_money(stcl),
            ltcl=_money(ltcl),
            brought_forward_stcl=_money(brought_forward_stcl),
            brought_forward_ltcl=_money(brought_forward_ltcl),
            slab_rate=Decimal(marginal_rate),
        ).to_dict()

    @staticmethod
    def harvest_opportunities(
        positions: list[dict[str, Any]],
        fy: str | None = None,
        as_of: str | None = None,
        realised_equity_ltcg: float = 0,
        realised_equity_stcg: float = 0,
    ) -> dict[str, Any]:
        """What to do with open holdings before 31 March, quantified."""
        return _harvest(
            [
                _Position(
                    name=str(p["name"]),
                    acquired_on=date.fromisoformat(p["acquired_on"]),
                    cost=_money(p["cost"]),
                    market_value=_money(p["market_value"]),
                    asset=str(p.get("asset", "listed_equity")),
                )
                for p in positions
            ],
            fy or current_fy(),
            as_of=date.fromisoformat(as_of) if as_of else date.today(),
            realised_equity_ltcg=_money(realised_equity_ltcg),
            realised_equity_stcg=_money(realised_equity_stcg),
        ).to_dict()

    @staticmethod
    def select_itr_form(
        profile: dict[str, Any],
        fy: str | None = None,
    ) -> dict[str, Any]:
        """Which ITR form to file, and why every simpler one was ruled out.

        Unknown profile keys are rejected rather than ignored. A typo'd
        `has_foreign_asset` silently dropping would make the selector
        recommend ITR-1 to someone who must disclose foreign holdings.
        """
        fields = set(_FilerProfile.__slots__)
        unknown = set(profile) - fields
        if unknown:
            raise ValueError(
                f"unknown filer profile field(s): {sorted(unknown)}. "
                f"Known fields: {sorted(fields)}"
            )

        kwargs: dict[str, Any] = {}
        for key, value in profile.items():
            if key == "entity":
                kwargs[key] = _EntityType(value)
            elif key == "residency":
                kwargs[key] = _Residency(value)
            elif key in ("total_income", "ltcg_112a", "agricultural_income"):
                kwargs[key] = _money(value)
            else:
                kwargs[key] = value

        return _select_itr_form(
            _FilerProfile(**kwargs), fy or current_fy()
        ).to_dict()

    @staticmethod
    def deadline_calendar(
        profile: dict[str, Any],
        fy: str | None = None,
        as_of: str | None = None,
    ) -> dict[str, Any]:
        """Only the deadlines this taxpayer actually has.

        Unknown keys are rejected rather than ignored, for the same reason as
        the ITR selector: a typo'd `is_audit_liable` silently dropping would
        tell a company's accountant 31 July.
        """
        fields = set(_TaxpayerProfile.__slots__)
        unknown = set(profile) - fields
        if unknown:
            raise ValueError(
                f"unknown taxpayer profile field(s): {sorted(unknown)}. "
                f"Known fields: {sorted(fields)}"
            )
        return _build_calendar(
            _TaxpayerProfile(**profile),
            fy or current_fy(),
            as_of=date.fromisoformat(as_of) if as_of else date.today(),
        ).to_dict()

    @staticmethod
    def optimise_salary_structure(
        structure: dict[str, Any],
        fy: str | None = None,
    ) -> dict[str, Any]:
        """Price each salary lever by recomputation, flagging those that need
        the employer to act."""
        fields = set(_SalaryStructure.__slots__)
        unknown = set(structure) - fields
        if unknown:
            raise ValueError(
                f"unknown salary structure field(s): {sorted(unknown)}. "
                f"Known fields: {sorted(fields)}"
            )
        money_fields = {
            "gross_salary", "basic_salary", "hra_received", "rent_paid",
            "employer_nps", "section_80c", "section_80d",
            "section_80ccd_1b", "home_loan_interest",
        }
        kwargs = {
            k: (_money(v) if k in money_fields else v)
            for k, v in structure.items()
        }
        return _optimise_salary(
            _SalaryStructure(**kwargs), fy or current_fy()
        ).to_dict()

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
