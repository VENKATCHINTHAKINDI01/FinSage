"""Deterministic tax computation.

Every function takes `fy: str` explicitly and never defaults to "current".
No function reads a global, a clock, or an environment variable.
"""

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
from backend.core.tax_engine.rebate import (
    apply_rebate_87a,
    rebate_ceiling,
    tax_free_gross_salary,
)
from backend.core.tax_engine.slabs import compute_slab_tax, marginal_rate
from backend.core.tax_engine.surcharge import compute_cess, compute_surcharge

__all__ = [
    "AssetClass",
    "CapitalGainsResult",
    "DeductionClaim",
    "DeductionOutcome",
    "Disposal",
    "TaxInput",
    "TaxResult",
    "apply_rebate_87a",
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
    "harvesting_headroom",
    "marginal_rate",
    "rebate_ceiling",
    "tax_free_gross_salary",
]
