"""Rule pack loader — CORE-001.

Rules are data. This turns a YAML pack into an immutable `TaxRuleset` and
refuses, loudly, to do anything clever.

Two design rules, both learned from v1:

  1. **No default financial year.** Every caller states which year it means.
     v1's engines implicitly meant "whatever was hardcoded", which is how they
     silently kept computing FY 2023-24 tax two years later. Revised returns
     and ITR-U (a 48-month window) need prior years to stay computable, so the
     year is always an argument, never an assumption.

  2. **Unknown year raises.** No falling back to the nearest pack. A wrong
     answer that looks right is worse than an error.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from functools import cache
from pathlib import Path
from types import MappingProxyType
from typing import Any

RULES_DIR = Path(__file__).resolve().parent
FY_PATTERN = re.compile(r"^\d{4}-\d{2}$")


class RuleError(Exception):
    """Raised when a rule pack is missing, malformed, or asked for a year it
    does not cover."""


# ── immutability ────────────────────────────────────────────────────────────

def _freeze(obj: Any) -> Any:
    """Deep-freeze the parsed YAML.

    A shared mutable ruleset is a race waiting to happen: one request
    normalising a rate in place would change every other request's tax.
    """
    if isinstance(obj, dict):
        return MappingProxyType({k: _freeze(v) for k, v in obj.items()})
    if isinstance(obj, list):
        return tuple(_freeze(v) for v in obj)
    return obj


@dataclass(frozen=True, slots=True)
class TaxRuleset:
    """One financial year's rules, immutable."""

    fy: str
    data: Mapping[str, Any]
    path: Path

    # ── metadata ────────────────────────────────────────────────────────────

    @property
    def meta(self) -> Mapping[str, Any]:
        return self.data["meta"]

    @property
    def assessment_year(self) -> str:
        return self.meta["assessment_year"]

    @property
    def governing_act(self) -> str:
        return self.meta["governing_act"]

    @property
    def verified_on(self) -> date:
        return _as_date(self.meta["verified_on"])

    @property
    def effective_from(self) -> date:
        return _as_date(self.meta["effective_from"])

    @property
    def effective_to(self) -> date:
        return _as_date(self.meta["effective_to"])

    @property
    def sources(self) -> tuple[str, ...]:
        return tuple(self.meta.get("sources", ()))

    @property
    def is_split_year(self) -> bool:
        """FY 2024-25 straddles the 23 July 2024 capital gains reform, so a
        transfer date is mandatory rather than optional that year."""
        return bool(self.data.get("capital_gains", {}).get("split_year", False))

    def covers(self, when: date) -> bool:
        return self.effective_from <= when <= self.effective_to

    def age_days(self, today: date) -> int:
        return (today - self.verified_on).days

    # ── sections ────────────────────────────────────────────────────────────

    def regime(self, name: str) -> Mapping[str, Any]:
        regimes = self.data["regimes"]
        if name not in regimes:
            raise RuleError(
                f"FY {self.fy} has no regime {name!r}; available: "
                f"{sorted(regimes)}"
            )
        return regimes[name]

    def slabs(self, regime: str, age: int = 0) -> tuple[Mapping[str, Any], ...]:
        """Slab bands for a regime, resolving the age band where one applies.

        The new regime has NO age bands — v1 auto-switched a 60-year-old to
        old-regime senior slabs inside a new-regime table, which taxed a
        62-year-old on ₹30L at a 20% top rate instead of 30%.
        """
        r = self.regime(regime)
        if not r.get("age_bands", False):
            return r["slabs"]
        if age >= 80 and "slabs_super_senior" in r:
            return r["slabs_super_senior"]
        if age >= 60 and "slabs_senior" in r:
            return r["slabs_senior"]
        return r["slabs"]

    def deduction(self, code: str) -> Mapping[str, Any]:
        code = code.upper().replace("(", "_").replace(")", "").replace(".", "_")
        table = self.data["deductions"]
        if code not in table:
            raise RuleError(
                f"FY {self.fy} has no deduction {code!r}; available: "
                f"{sorted(table)}"
            )
        return table[code]

    def has_deduction(self, code: str) -> bool:
        try:
            self.deduction(code)
        except RuleError:
            return False
        return True

    def deduction_allowed_in(self, code: str, regime: str) -> bool:
        allowed = self.regime(regime).get("allowed_deductions")
        if allowed == "all_chapter_via":
            return True
        return code.upper() in {str(a).upper() for a in (allowed or ())}

    @property
    def surcharge(self) -> Mapping[str, Any]:
        return self.data["surcharge"]

    @property
    def cess_rate(self) -> Decimal:
        return Decimal(self.data["cess"]["rate"])

    @property
    def capital_gains(self) -> Mapping[str, Any]:
        return self.data["capital_gains"]

    @property
    def presumptive(self) -> Mapping[str, Any]:
        return self.data["presumptive"]

    @property
    def advance_tax(self) -> Mapping[str, Any]:
        return self.data["advance_tax"]

    @property
    def deadlines(self) -> Mapping[str, Any]:
        return self.data["deadlines"]

    def cii(self, fy: str) -> int:
        table = self.data.get("cost_inflation_index", {})
        if fy not in table:
            raise RuleError(f"no Cost Inflation Index for FY {fy}")
        return int(table[fy])

    def __repr__(self) -> str:
        return f"TaxRuleset(fy={self.fy!r}, act={self.governing_act!r})"


# ── loading ─────────────────────────────────────────────────────────────────

def _as_date(v: Any) -> date:
    if isinstance(v, date):
        return v
    return datetime.strptime(str(v), "%Y-%m-%d").date()


def _pack_path(fy: str) -> Path:
    return RULES_DIR / f"fy_{fy.replace('-', '_')}.yaml"


def available_years() -> tuple[str, ...]:
    years = []
    for p in RULES_DIR.glob("fy_*.yaml"):
        stem = p.stem.removeprefix("fy_").split("_")
        if len(stem) == 2:
            years.append(f"{stem[0]}-{stem[1]}")
    return tuple(sorted(years))


@cache
def load_ruleset(fy: str) -> TaxRuleset:
    """Load the rule pack for a financial year.

    `fy` is mandatory and in "2026-27" form. There is deliberately no default
    and no fallback: an unknown year raises rather than quietly returning the
    nearest pack.
    """
    if not isinstance(fy, str) or not FY_PATTERN.match(fy):
        raise RuleError(
            f"financial year must look like '2026-27', got {fy!r}"
        )

    path = _pack_path(fy)
    if not path.exists():
        raise RuleError(
            f"no rule pack for FY {fy}. Available: {', '.join(available_years())}. "
            f"Rules are data — add {path.name} rather than special-casing code."
        )

    import yaml

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RuleError(f"{path.name} did not parse to a mapping")

    for key in ("meta", "regimes", "surcharge", "cess", "deductions"):
        if key not in raw:
            raise RuleError(f"{path.name} is missing required section {key!r}")

    declared = raw["meta"].get("financial_year")
    if declared != fy:
        raise RuleError(
            f"{path.name} declares financial_year {declared!r} but was loaded "
            f"as {fy!r}"
        )

    for key in ("assessment_year", "effective_from", "effective_to",
                "governing_act", "verified_on"):
        if not raw["meta"].get(key):
            raise RuleError(f"{path.name}: meta.{key} is required")

    return TaxRuleset(fy=fy, data=_freeze(raw), path=path)


def ruleset_for_date(when: date) -> TaxRuleset:
    """Resolve the pack covering a date — for a transfer or payment whose FY
    is implied rather than stated."""
    for fy in available_years():
        rs = load_ruleset(fy)
        if rs.covers(when):
            return rs
    raise RuleError(
        f"no rule pack covers {when.isoformat()}. "
        f"Available: {', '.join(available_years())}"
    )


def fy_for_date(when: date) -> str:
    """Indian financial year runs 1 April to 31 March."""
    return (
        f"{when.year}-{str(when.year + 1)[-2:]}"
        if when.month >= 4
        else f"{when.year - 1}-{str(when.year)[-2:]}"
    )
