"""Versioned tax rule packs. Rules are DATA, not code.

Adding FY 2027-28 after the next Budget is one new YAML file plus one golden
test file — no Python changes.

Each pack carries `meta.verified_on`. scripts/verify_freshness.py fails the
build when a pack backing a shipped feature goes stale, which is the control
that stops v1's silent two-year decay from recurring.
"""

from backend.core.rules.aliases import Alias, AliasMap, cite, load_aliases, unverified_aliases
from backend.core.rules.loader import (
    RuleError,
    TaxRuleset,
    available_years,
    fy_for_date,
    load_ruleset,
    ruleset_for_date,
)

__all__ = [
    "Alias",
    "AliasMap",
    "RuleError",
    "TaxRuleset",
    "available_years",
    "cite",
    "fy_for_date",
    "load_aliases",
    "load_ruleset",
    "ruleset_for_date",
    "unverified_aliases",
]
