"""DeductionHunterAgent — AGT-001.

Locks in two fixes:
  - `_identify_deductions` used to ask the LLM for an "estimated deductible
    amount" even when the user never stated one — a plausible-sounding guess
    presented as a number. The prompt now requires `amount_known: false` /
    `amount: null` when no real figure exists, and the agent must not
    silently treat that as zero.
  - The HRA branch read `hra_data["exempt_hra"]` as if it were already a
    float; it is a decimal string (Money.to_json()), and `> 0` /
    `:,.0f`-formatting a string crashed this whole branch on every real
    (non-mocked) calculate_hra_exemption result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from backend.agents.deduction_hunter import DeductionHunterAgent
from backend.tools.calculation import TaxCalculationEngine


@dataclass
class FakeLLMResponse:
    text: str


class FakeLLM:
    async def complete(self, prompt: str, **kwargs) -> FakeLLMResponse:
        return FakeLLMResponse(text=self._json)

    def __init__(self, json_text: str) -> None:
        self._json = json_text


class MockTools:
    def __init__(self, annual_income: float = 1200000) -> None:
        self.annual_income = annual_income

    def list_tools(self) -> list[str]:
        return ["get_user_profile", "semantic_search_tax_kb", "calculate_hra_exemption",
                "calculate_deduction_impact", "get_scheme_details", "calculate_tax_liability",
                "generate_tax_report"]

    async def execute_tool(self, name: str, **kwargs) -> dict[str, Any]:
        if name == "get_user_profile":
            return {"success": True, "result": {"financial_profile": {"annual_income": self.annual_income}}}
        if name == "semantic_search_tax_kb":
            return {"success": True, "result": {"context": ""}}
        if name == "calculate_deduction_impact":
            result = TaxCalculationEngine.calculate_deduction_benefit(
                deduction_amount=kwargs["deduction_amount"],
                current_taxable_income=kwargs["current_taxable_income"],
                regime="old",
            )
            return {"success": True, "result": result}
        if name == "get_scheme_details":
            return {"success": True, "result": {"details": {}}}
        if name == "calculate_tax_liability":
            return {"success": True, "result": {"total_tax_liability": 0}}
        if name == "generate_tax_report":
            return {"success": True, "result": {}}
        if name == "calculate_hra_exemption":
            return {"success": True, "result": {"exempt_hra": "84000.00", "taxable_hra": "36000.00"}}
        return {"success": False, "error": f"unmocked tool {name}"}


DEDUCTION_WITH_NO_STATED_AMOUNT = """{
  "deductions": [
    {
      "category": "Home Office",
      "description": "no amount mentioned by the user",
      "amount": null,
      "amount_known": false,
      "confidence": "medium",
      "filing_requirement": "Schedule Business income",
      "documentation": "receipts",
      "scheme_code": null
    }
  ]
}"""


@pytest.mark.asyncio
async def test_an_unstated_amount_gets_no_fabricated_tax_savings(monkeypatch):
    monkeypatch.setattr(
        "backend.agents.deduction_hunter.get_llm",
        lambda: FakeLLM(DEDUCTION_WITH_NO_STATED_AMOUNT),
    )
    agent = DeductionHunterAgent()
    output = await agent.execute("I work from home sometimes", {"user_id": "u1"}, tools=MockTools())

    assert output.status == "success"
    deduction = output.result["deductions"][0]
    assert deduction["amount"] is None
    assert deduction["tax_savings"] is None
    assert "Home Office" in output.result["amount_needed_from_user"]
    # The unstated deduction must not be counted in the aggregate.
    assert output.result["total_deduction_amount"] == 0


@pytest.mark.asyncio
async def test_hra_branch_does_not_crash_on_the_real_string_typed_tool_result(monkeypatch):
    """Regression test for a real, pre-existing bug: `calculate_hra_exemption`
    returns decimal strings (Money.to_json()); this branch compared one with
    `> 0` and format-specced another with `:,.0f`, both of which raise on a
    str. Never caught because no test exercised this path with a
    non-numeric-looking mock before."""
    monkeypatch.setattr(
        "backend.agents.deduction_hunter.get_llm",
        lambda: FakeLLM('{"deductions": []}'),
    )
    agent = DeductionHunterAgent()
    output = await agent.execute(
        "I pay rent and want to claim HRA", {"user_id": "u1"},
        tools=MockTools(),
    )

    assert output.status == "success", output.result
    hra = next(d for d in output.result["deductions"] if d["category"] == "HRA Exemption")
    assert hra["amount"] == 84000.0
    assert isinstance(hra["tax_savings"], float)
