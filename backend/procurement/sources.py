"""Source gathering — PRC-002 (the I/O half).

The pure types live in `backend.core.provenance.sourcing` because core is
forbidden from importing this package, and the tier invariant belongs beside
Money and Trace rather than beside HTTP clients. Re-exported here so the
fetchers have one import site.
"""

from __future__ import annotations

from backend.core.provenance.sourcing import (
    DEFAULT_TTL_DAYS,
    TTL_DAYS,
    CanaryResult,
    CostLine,
    SourceCache,
    SourcedFact,
    Tier,
    Tier3CannotCost,
    UndatedFact,
    canary_verdict,
    next_refresh_due,
)

__all__ = [
    "DEFAULT_TTL_DAYS",
    "TTL_DAYS",
    "CanaryResult",
    "CostLine",
    "SourceCache",
    "SourcedFact",
    "Tier",
    "Tier3CannotCost",
    "UndatedFact",
    "canary_verdict",
    "next_refresh_due",
]
