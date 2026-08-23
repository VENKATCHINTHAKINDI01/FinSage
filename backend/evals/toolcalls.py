"""Deterministic tool results for a scenario — AGT-005.

The gap this closes
-------------------
`run_scenario(..., live=True)` raised `NotImplementedError`, and the three
fixtures that do exist were made by a standalone script with hand-built
`tool_results` per scenario. That is why ten of the fifteen scenarios have no
fixture: there was no generic way to produce one, so each needed bespoke code
nobody was going to write fifteen times.

The missing abstraction is small: a scenario should DECLARE what the agent is
allowed to see, and the runner should build it. So a scenario carries an
optional `tools:` block —

    tools:
      - tool: compute_tax
        args: {salary: 1500000, deductions: {"80C": 150000}}
      - tool: compute_capital_gains
        args:
          disposals:
            - {asset: equity, acquired_on: "2022-01-01", sold_on: "2026-06-01",
               cost: 300000, consideration: 500000}

— and everything below turns that into the `tool_results` the pipeline
receives. Where a scenario declares nothing, `compute_tax` is derived from its
profile, which covers most of them.

Why this file imports the CORE and not the tool registry
---------------------------------------------------------
The registry is async, carries a database session and wraps results in a
success envelope. An eval needs none of that and must not depend on any of it:
the whole point of the offline suite is that a scenario replays with no
network, no database and no clock. These call `backend.core` directly, which is
pure by contract.

The figures here are the GROUND TRUTH the scorer checks against
----------------------------------------------------------------
`numeric_provenance` fails any number in the model's answer that is not in a
tool result. So a bug in this file does not produce a wrong eval score — it
produces a scenario where every correct answer is marked fabricated. That is
why the dispatch is a closed set with no fallback: an unknown tool name raises
rather than returning an empty result that would fail every claim.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from backend.core.provenance.money import Money
from backend.core.rules.loader import load_ruleset
from backend.core.tax_engine.capital_gains import (
    AssetClass,
    Disposal,
    compute_capital_gains,
)
from backend.core.tax_engine.compute import TaxInput, compute_tax


class UnknownEvalTool(Exception):
    """A scenario named a tool the harness cannot produce.

    Raised rather than skipped. A missing tool result means the scorer sees no
    grounding for any figure, so every correct answer fails — a silent empty
    result would look like the model fabricating and send someone hunting a
    bug in the agent.
    """


def _money(value: Any) -> Money:
    return Money(str(value)) if value is not None else Money(0)


def _tax(profile: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    """`compute_tax`, from the scenario profile plus any overrides."""
    merged = {**profile, **args}
    fy = str(merged.get("fy", "2026-27"))
    deductions = {
        code: _money(amount)
        for code, amount in (merged.get("deductions") or {}).items()
    }
    result = compute_tax(TaxInput(
        fy=fy,
        regime=str(merged.get("regime", "new")),
        age=int(merged.get("age", 0)),
        salary=_money(merged.get("salary", 0)),
        house_property=_money(merged.get("house_property", 0)),
        business=_money(merged.get("business", 0)),
        other_sources=_money(merged.get("other_sources", 0)),
        special_rate_tax=_money(merged.get("special_rate_tax", 0)),
        special_rate_income=_money(merged.get("special_rate_income", 0)),
        deductions=deductions,
    ))
    return result.to_dict()


def _capital_gains(profile: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    """`compute_capital_gains` from declared disposals.

    Dates are mandatory and not defaulted. The holding period and the
    23 July 2024 boundary are the entire question for most of these scenarios;
    a defaulted date would decide the answer before the engine ran.
    """
    fy = str(args.get("fy", profile.get("fy", "2026-27")))
    disposals = []
    for d in args.get("disposals", []):
        disposals.append(Disposal(
            asset=AssetClass(d.get("asset", "other")),
            acquired_on=date.fromisoformat(str(d["acquired_on"])),
            sold_on=date.fromisoformat(str(d["sold_on"])),
            cost=_money(d.get("cost", 0)),
            consideration=_money(d.get("consideration", 0)),
            improvement_cost=_money(d.get("improvement_cost", 0)),
            transfer_expenses=_money(d.get("transfer_expenses", 0)),
            description=str(d.get("description", "")),
        ))
    result = compute_capital_gains(disposals, load_ruleset(fy))
    return {
        "fy": fy,
        "equity_ltcg_gross": result.equity_ltcg_gross.to_json(),
        "equity_ltcg_exemption": result.equity_ltcg_exemption.to_json(),
        "equity_ltcg_taxable": result.equity_ltcg_taxable.to_json(),
        "equity_stcg": result.equity_stcg.to_json(),
        "other_ltcg": result.other_ltcg.to_json(),
        "slab_taxed_gains": result.slab_taxed_gains.to_json(),
        "total_tax": result.total_tax.to_json(),
        "notes": list(result.notes),
        "worksheet": result.trace.render(),
    }


def _rates(profile: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    """The statutory rates for the year.

    Present so a scenario that asks "what is the LTCG rate" has the rate in a
    tool result rather than relying on the model to remember it — which is the
    exact behaviour `numeric_provenance` exists to fail.
    """
    fy = str(args.get("fy", profile.get("fy", "2026-27")))
    rs = load_ruleset(fy)
    cg = rs.capital_gains
    return {
        "fy": fy,
        "cess_rate": str(rs.cess_rate),
        "equity_ltcg_rate": str(cg["equity_ltcg"]["rate"]),
        "equity_ltcg_annual_exemption": str(cg["equity_ltcg"]["annual_exemption"]),
        "equity_ltcg_holding_months": str(cg["equity_ltcg"]["holding_months"]),
        "equity_stcg_rate": str(cg["equity_stcg"]["rate"]),
        "other_ltcg_rate": str(cg["other_ltcg"]["rate"]),
        "regime_change_date": str(cg["regime_change_date"]),
    }


DISPATCH = {
    "compute_tax": _tax,
    "compute_capital_gains": _capital_gains,
    "statutory_rates": _rates,
}


def results_for(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    """Everything the agent is permitted to see for this scenario.

    A scenario with no `tools:` block gets `compute_tax` from its profile,
    because that is what nearly every tax question needs and requiring the
    boilerplate everywhere would just mean it gets copied wrongly.
    """
    profile = dict(scenario.get("profile") or {})
    declared = scenario.get("tools")

    if not declared:
        declared = [{"tool": "compute_tax", "args": {}}]

    out: list[dict[str, Any]] = []
    for spec in declared:
        name = str(spec.get("tool", ""))
        fn = DISPATCH.get(name)
        if fn is None:
            raise UnknownEvalTool(
                f"scenario {scenario.get('id')!r} asks for tool {name!r}, which "
                f"the eval harness cannot produce. Known: {sorted(DISPATCH)}. "
                f"Returning nothing instead would make every figure in a "
                f"correct answer look fabricated."
            )
        out.append({
            "tool": name,
            "success": True,
            "result": fn(profile, dict(spec.get("args") or {})),
        })
    return out


__all__ = ["DISPATCH", "UnknownEvalTool", "results_for"]
