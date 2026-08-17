"""Deterministic tax computation.

Every function takes `fy: str` explicitly and never defaults to "current".
No function reads a global, a clock, or an environment variable.
"""

from backend.core.tax_engine.advance_tax import (
    AdvanceTaxPlan,
    Instalment,
    RefundInterest,
    plan_advance_tax,
    refund_interest,
)
from backend.core.tax_engine.capital_gains import (
    AssetClass,
    CapitalGainsResult,
    Disposal,
    compute_capital_gains,
    harvesting_headroom,
)
from backend.core.tax_engine.compute import (
    TaxInput,
    TaxResult,
    compute_tax,
    compute_total_tax,
)
from backend.core.tax_engine.deadlines import (
    Calendar,
    Deadline,
    TaxpayerProfile,
    Urgency,
    build_calendar,
    itr_due_date,
)
from backend.core.tax_engine.deductions import (
    DeductionClaim,
    DeductionOutcome,
    compute_80ccd2,
    compute_80cce_group,
    compute_80d,
    compute_80ddb,
    compute_disability,
    compute_hra_exemption,
    compute_interest_deduction,
    filter_by_regime,
)
from backend.core.tax_engine.harvesting import (
    Allocation,
    GainBucket,
    HarvestPlan,
    Opportunity,
    Position,
    SetOffResult,
    harvest,
    set_off_losses,
)
from backend.core.tax_engine.itr_form import (
    EntityType,
    Exclusion,
    FilerProfile,
    FormRecommendation,
    Residency,
    select_itr_form,
)
from backend.core.tax_engine.rebate import (
    apply_rebate_87a,
    rebate_ceiling,
    tax_free_gross_salary,
)
from backend.core.tax_engine.regime_compare import (
    RegimeComparison,
    breakeven_deductions,
    compare_regimes,
    comparison_trace,
    payable,
)
from backend.core.tax_engine.salary_structure import (
    Lever,
    SalaryStructure,
    StructuringPlan,
    optimise_salary,
)
from backend.core.tax_engine.slabs import compute_slab_tax, marginal_rate
from backend.core.tax_engine.surcharge import compute_cess, compute_surcharge

__all__ = [
    "AdvanceTaxPlan",
    "Allocation",
    "AssetClass",
    "Calendar",
    "CapitalGainsResult",
    "Deadline",
    "DeductionClaim",
    "DeductionOutcome",
    "Disposal",
    "EntityType",
    "Exclusion",
    "FilerProfile",
    "FormRecommendation",
    "GainBucket",
    "HarvestPlan",
    "Instalment",
    "Lever",
    "Opportunity",
    "Position",
    "RefundInterest",
    "RegimeComparison",
    "Residency",
    "SalaryStructure",
    "SetOffResult",
    "StructuringPlan",
    "TaxInput",
    "TaxResult",
    "TaxpayerProfile",
    "Urgency",
    "apply_rebate_87a",
    "breakeven_deductions",
    "build_calendar",
    "compare_regimes",
    "comparison_trace",
    "compute_80ccd2",
    "compute_80cce_group",
    "compute_80d",
    "compute_80ddb",
    "compute_capital_gains",
    "compute_cess",
    "compute_disability",
    "compute_hra_exemption",
    "compute_interest_deduction",
    "compute_slab_tax",
    "compute_surcharge",
    "compute_tax",
    "compute_total_tax",
    "filter_by_regime",
    "harvest",
    "harvesting_headroom",
    "itr_due_date",
    "marginal_rate",
    "optimise_salary",
    "payable",
    "plan_advance_tax",
    "rebate_ceiling",
    "refund_interest",
    "select_itr_form",
    "set_off_losses",
    "tax_free_gross_salary",
]
