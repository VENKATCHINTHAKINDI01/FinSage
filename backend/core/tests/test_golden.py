"""Layer 1 — golden tax tests.

A golden case is a verified (input → exact expected output) pair. Every case
must record `verified_against`: where a human confirmed the expected value.
An expected value nobody checked is just the implementation restated.

Cases live in `golden/<fy>/*.yaml`. See that directory for the format.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from backend.core.provenance.money import Money
from backend.core.tax_engine import TaxInput, compute_tax

# Only the compute_tax corpus. Sibling directories under golden/ hold corpora
# for other engines with different case shapes — `regime_comparison/` is loaded
# by test_regime_compare.py. An earlier layout put them all in one tree, and
# this loader tried to parse a regime-comparison case as a TaxResult.
GOLDEN = Path(__file__).resolve().parent / "golden" / "tax_computation"

REQUIRED_KEYS = {"id", "fy", "input", "expect", "verified_against"}

# Fields a case may assert on, mapped to TaxResult attributes.
ASSERTABLE = {
    "gross_total_income",
    "total_deductions",
    "taxable_income",
    "tax_on_slabs",
    "special_rate_tax",
    "rebate_87a",
    "tax_after_rebate",
    "surcharge",
    "pre_cess_liability",
    "cess",
    "total_tax_exact",
    "total_tax",
    "balance_payable",
    "refund_due",
}

# Every threshold where the tax function changes shape. A cliff bug hides at a
# boundary or nowhere, so a corpus that skips these is not doing its job.
REQUIRED_BOUNDARIES = {
    "2026-27": {
        400000,     # first slab edge
        1200000,    # 87A rebate ceiling, new regime
        2400000,    # 30% slab entry
        5000000,    # surcharge 10% threshold
    }
}


def _load(path: Path) -> list[dict[str, Any]]:
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not data:
        return []
    return data if isinstance(data, list) else [data]


def all_cases() -> list[tuple[Path, dict[str, Any]]]:
    if not GOLDEN.exists():
        return []
    return [(p, case) for p in sorted(GOLDEN.rglob("*.y*ml")) for case in _load(p)]


CASES = all_cases()
IDS = [c.get("id", f"case-{i}") for i, (_p, c) in enumerate(CASES)]


def _money(value: Any) -> Money:
    """Build Money from a YAML scalar.

    Money refuses float by design, but YAML parses `10.40` as one. Routing
    through `str` recovers the written decimal exactly (`str(10.40)` is
    `'10.4'`), so the corpus can express paise without weakening the rule that
    production code never touches a float in a money path.
    """
    if isinstance(value, float):
        return Money(str(value))
    return Money(value)


def _build_input(case: dict[str, Any]) -> TaxInput:
    raw = dict(case["input"])
    built = TaxInput(
        fy=case["fy"],
        regime=case.get("regime", "new"),
        age=int(raw.pop("age", 0)),
        salary=_money(raw.pop("salary", 0)),
        house_property=_money(raw.pop("house_property", 0)),
        business=_money(raw.pop("business", 0)),
        other_sources=_money(raw.pop("other_sources", 0)),
        special_rate_tax=_money(raw.pop("special_rate_tax", 0)),
        special_rate_income=_money(raw.pop("special_rate_income", 0)),
        taxes_paid=_money(raw.pop("taxes_paid", 0)),
        deductions={k: _money(v) for k, v in (raw.pop("deductions", {}) or {}).items()},
        exemptions={k: _money(v) for k, v in (raw.pop("exemptions", {}) or {}).items()},
    )
    # Anything left over is a typo in the case. Fail loudly: a silently ignored
    # input field would make a golden case assert on a computation that never
    # used half its inputs.
    if raw:
        pytest.fail(f"{case['id']}: unknown input fields {sorted(raw)}")
    return built


# ── the actual assertions ───────────────────────────────────────────────────

@pytest.mark.golden
@pytest.mark.skipif(not CASES, reason="golden corpus is empty")
@pytest.mark.parametrize("path,case", CASES, ids=IDS)
def test_golden_case(path: Path, case: dict[str, Any]) -> None:
    result = compute_tax(_build_input(case))

    mismatches = []
    for field_name, expected in case["expect"].items():
        assert field_name in ASSERTABLE, (
            f"{case['id']}: '{field_name}' is not assertable; "
            f"choose from {sorted(ASSERTABLE)}"
        )
        actual = getattr(result, field_name)
        if actual != _money(expected):
            # Exact decimals, not the display format. `₹10` and `₹10.40` both
            # render as "₹10", which made the first run of this suite report
            # "expected ₹10, got ₹10" — technically true and entirely useless.
            mismatches.append(
                f"    {field_name}: expected {_money(expected).amount}, "
                f"got {actual.amount}  (difference {actual.amount - _money(expected).amount})"
            )

    if mismatches:
        pytest.fail(
            f"\n{case['id']} ({path.name})\n"
            + "\n".join(mismatches)
            + f"\n  verified against: {case['verified_against'].strip()}\n\n"
            + result.trace.render()
        )


@pytest.mark.golden
@pytest.mark.skipif(not CASES, reason="golden corpus is empty")
@pytest.mark.parametrize("path,case", CASES, ids=IDS)
def test_golden_case_trace_replays(path: Path, case: dict[str, Any]) -> None:
    """The worksheet shown to the user must be the computation that ran.

    Without this, "show the math" is a plausible narrative that may not match
    the answer above it.
    """
    result = compute_tax(_build_input(case))
    problems = result.trace.verify()
    assert not problems, f"{case['id']}: trace does not replay:\n  " + "\n  ".join(problems)


# ── corpus hygiene ──────────────────────────────────────────────────────────

@pytest.mark.skipif(not CASES, reason="golden corpus is empty")
@pytest.mark.parametrize("path,case", CASES, ids=IDS)
def test_case_is_well_formed(path: Path, case: dict[str, Any]) -> None:
    missing = REQUIRED_KEYS - case.keys()
    assert not missing, f"{path.name}:{case.get('id', '?')} missing {sorted(missing)}"
    assert case["verified_against"].strip(), (
        f"{case['id']}: verified_against is empty. An expected value nobody "
        f"checked against an official source is not a golden case."
    )
    assert case["expect"], f"{case['id']}: expect block is empty"


@pytest.mark.skipif(not CASES, reason="golden corpus is empty")
def test_case_ids_are_unique() -> None:
    ids = [c["id"] for _, c in CASES]
    dupes = {i for i in ids if ids.count(i) > 1}
    assert not dupes, f"duplicate golden case ids: {sorted(dupes)}"


@pytest.mark.skipif(not CASES, reason="golden corpus is empty")
@pytest.mark.parametrize("fy", sorted(REQUIRED_BOUNDARIES))
def test_boundaries_are_covered(fy: str) -> None:
    """Refuse to call a corpus complete while it dodges the cliff edges."""
    covered: set[int] = set()
    for _p, c in CASES:
        if c.get("fy") != fy:
            continue
        covered.update(v for v in c.get("input", {}).values() if isinstance(v, int))
        covered.update(v for v in c.get("expect", {}).values() if isinstance(v, int))

    missing = REQUIRED_BOUNDARIES[fy] - covered
    assert not missing, (
        f"FY {fy} golden corpus does not exercise these boundaries: {sorted(missing)}"
    )


def test_corpus_layout_is_valid() -> None:
    if not GOLDEN.exists():
        pytest.skip("golden/ not created yet")
    for p in GOLDEN.rglob("*"):
        if p.is_file() and p.name != ".gitkeep":
            assert p.suffix in {".yaml", ".yml"}, f"unexpected file in corpus: {p.name}"
