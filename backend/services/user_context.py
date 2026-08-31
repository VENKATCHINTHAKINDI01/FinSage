"""
Builds the `user_context` dict every agent-invoking endpoint needs, from
the user's real saved financial profile.

Consolidated here — this used to be reimplemented independently in at
least two places (api/compliance.py's own fetch_user_context, and
api/chat.py's much thinner get_user_context, which only read
annual_income/employment_type and left age/tax_regime/deductions to
per-endpoint `getattr(current_user, "age", 35)`-style fallbacks that
always hit the default, since none of those attributes exist on the bare
auth/User record). api/benefits.py and api/suggestions.py already had the
same bug fixed by switching to this function directly; api/chat.py is the
one production caller that hadn't been.

Every endpoint that invokes an agent should build its user_context from
this, not a bespoke query — a second independent implementation is
exactly how the DEM-002/AGT-001 fabricated-figure bugs kept recurring:
one copy gets fixed, a sibling copy silently doesn't.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.orm_models import FinancialProfile


async def fetch_user_context(user_id: str, email: str, session: AsyncSession) -> dict[str, Any]:
    result_profile = await session.execute(
        select(FinancialProfile).where(FinancialProfile.user_id == user_id)
    )
    profile_rec = result_profile.scalar_one_or_none()
    profile_data = profile_rec.profile_data if (profile_rec and profile_rec.profile_data) else {}

    # Calculate gross income
    salary_ctc = float(profile_data.get("salaryCtc", 0.0))
    profession = profile_data.get("profession", "")
    business_inc = float(profile_data.get("businessIncome", 0.0))
    freelance_inc = float(profile_data.get("freelanceIncome", 0.0))
    rental_inc = float(profile_data.get("rentalIncome", 0.0))
    cg_stcg = float(profile_data.get("capitalGainsStcg", 0.0))
    cg_ltcg = float(profile_data.get("capitalGainsLtcg", 0.0))
    other_inc = float(profile_data.get("otherIncome", 0.0))
    div_inc = float(profile_data.get("dividendIncome", 0.0))

    gross_income = (
        (salary_ctc if profession == "salaried" else 0.0) +
        business_inc +
        freelance_inc +
        rental_inc +
        cg_stcg +
        cg_ltcg +
        other_inc +
        div_inc
    )

    # Deductions
    ppf = float(profile_data.get("ppf", 0.0))
    elss = float(profile_data.get("elss", 0.0))
    lic = float(profile_data.get("lic", 0.0))
    ulip = float(profile_data.get("ulip", 0.0))
    fd5yr = float(profile_data.get("fd5yr", 0.0))
    nsc = float(profile_data.get("nsc", 0.0))
    sukanya = float(profile_data.get("sukanyaSamriddhi", 0.0))
    hl_principal = float(profile_data.get("homeLoanPrincipal", 0.0))

    total_80c = min(150000.0, ppf + elss + lic + ulip + fd5yr + nsc + sukanya + hl_principal)
    nps_emp = float(profile_data.get("npsEmployee", 0.0))
    total_80ccd = min(50000.0, nps_emp)
    health_self = float(profile_data.get("healthInsuranceSelf", 0.0))
    health_parents = float(profile_data.get("healthInsuranceParents", 0.0))
    total_80d = min(25000.0, health_self) + min(50000.0, health_parents)
    hl_interest = float(profile_data.get("homeLoanInterest", 0.0))
    sec24b = min(200000.0, hl_interest)

    deductions_dict = {
        "80c": total_80c,
        "80d": total_80d,
        "nps": total_80ccd,
        "home_loan_interest": sec24b,
        "ev_loan_interest": float(profile_data.get("evLoanInterest", 0.0)),
        "education_loan_interest": float(profile_data.get("eduLoanInterest", 0.0)),
        "savings_interest": float(profile_data.get("savingsBankInterest", 0.0)),
        "donations": float(profile_data.get("donationsU80G", 0.0)),
        "hra": float(profile_data.get("hra", 0.0)),
        "lta": float(profile_data.get("lta", 0.0))
    }

    return {
        "user_id": user_id,
        "email": email,
        "age": profile_data.get("age") or 35,
        "tax_regime": profile_data.get("taxRegime") or "new",
        "annual_income": gross_income,
        "employment_type": profession or "salaried",
        "tds_paid": float(profile_data.get("tds_paid", 0.0)),
        "deductions": deductions_dict,
        "gst_registered": profession in ["business_owner", "professional", "freelancer"],
        "advance_tax_paid": float(profile_data.get("advance_tax_paid", 0.0)),
        "has_capital_gains": cg_stcg > 0 or cg_ltcg > 0,
        "calculated_tax": 0.0,
        "form_16_tds": float(profile_data.get("form_16_tds", 0.0)),
        "turnover": float(profile_data.get("turnover", 0.0)),
        "long_term_gains": cg_ltcg,
        "short_term_gains": cg_stcg,
        "losses": profile_data.get("losses") or {}
    }
