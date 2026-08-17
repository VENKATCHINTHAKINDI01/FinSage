"""Agents may only ever see the figure the taxpayer actually pays.

`TaxResult` carries two numbers: `total_tax_exact` (the liability to the paisa)
and `total_tax` (that figure rounded to the nearest ₹10 under s.288B, which is
what a demand notice states). Only the second may cross the boundary into an
agent's context.

This is not pedantry. The governing rule of the whole system is that no rupee
figure shown to a user may originate from a language model — every figure has
to come from the engine. That guarantee is worth nothing if the engine hands
the model two different numbers for the same quantity and lets it choose.

The bug this pins shut: the fields were originally named `total_tax` for the
exact value and `total_tax_rounded` for the payable one, so every consumer that
reached for the obvious name got the wrong one. Ten call sites in this adapter
were serialising ₹97,502.08 for a taxpayer whose demand reads ₹97,500.
"""

from __future__ import annotations

import ast
import json
import pathlib

import pytest

from backend.core.provenance.money import Money
from backend.tools.calculation import TaxCalculationEngine

ADAPTER = pathlib.Path(__file__).resolve().parents[1] / "calculation.py"


# Every adapter method an agent can call, with arguments that exercise it.
TOOL_CALLS = [
    ("calculate_income_tax", {"taxable_income": 1_500_000, "fy": "2026-27"}),
    ("calculate_tax_with_deductions",
     {"gross_income": 1_500_000, "fy": "2026-27", "deductions": {"80C": 150_000}}),
    ("compare_regimes", {"gross_income": 1_500_000, "fy": "2026-27",
                        "deductions": {"80C": 150_000}}),
    ("calculate_deduction_benefit",
     {"deduction_amount": 150_000, "current_taxable_income": 1_500_000,
      "fy": "2026-27"}),
]


@pytest.mark.parametrize("method,kwargs", TOOL_CALLS, ids=[m for m, _ in TOOL_CALLS])
class TestTheAdapterNeverSerialisesTheExactLiability:
    def test_no_tool_result_carries_the_exact_liability(self, method, kwargs) -> None:
        result = getattr(TaxCalculationEngine, method)(**kwargs)
        assert "total_tax_exact" not in json.dumps(result, default=str), (
            "the exact liability must not cross into an agent's context; only "
            "the s.288B payable figure may"
        )

    def test_every_rupee_figure_is_a_whole_number_of_rupees(
        self, method, kwargs
    ) -> None:
        """Paisa in a tool result means an unrounded intermediate escaped."""
        result = getattr(TaxCalculationEngine, method)(**kwargs)
        for key in ("total_tax", "balance_payable", "refund_due", "saving",
                    "tax_before", "tax_after"):
            if isinstance(result.get(key), str):
                assert Money(result[key]).amount % 1 == 0, (
                    f"{method}: {key}={result[key]} carries paisa, so it is "
                    f"not the s.288B figure"
                )


def test_the_reported_figure_is_the_payable_one() -> None:
    """An income chosen so the two genuinely differ: s.87A marginal relief
    leaves an exact liability of ₹10.40, which s.288B rounds to ₹10."""
    result = TaxCalculationEngine.calculate_income_tax(
        taxable_income=1_200_010, fy="2026-27", regime="new"
    )
    assert Money(result["total_tax"]) == Money(10)


def test_no_attribute_access_to_total_tax_exact_anywhere_in_the_adapter() -> None:
    """Source-level guard, because a future method could reintroduce it on a
    path the fixtures above never exercise."""
    tree = ast.parse(ADAPTER.read_text(encoding="utf-8"))
    offenders = [
        f"line {node.lineno}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "total_tax_exact"
    ]
    assert not offenders, (
        "backend/tools/calculation.py is the boundary between the engine and "
        "the agents. It must read only the payable figure. Found at: "
        + ", ".join(offenders)
    )
