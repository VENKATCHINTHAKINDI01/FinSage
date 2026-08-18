"""TaxOptimizerAgent — AGT-001.

Locks in the fix: `_generate_strategies` used to ask the LLM directly for a
rupee `estimated_savings` per strategy, then fed that guess into
`calculate_deduction_impact` as if it were a real deduction amount — a real
tool call downstream of a fabricated input is still a fabricated result. The
LLM now supplies only qualitative fields; every rupee figure that survives
into `strategy["savings"]` comes from `calculate_deduction_impact` against a
scheme's real statutory limit (`get_scheme_details`), never from the model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from backend.agents.tax_optimizer import TaxOptimizerAgent
from backend.tools.calculation import TaxCalculationEngine


@dataclass
class FakeLLMResponse:
    text: str


class FakeLLM:
    """Always tries to smuggle a rupee figure into the response, so a test
    that only checked the prompt wording could not give a false pass."""

    def __init__(self, strategies_json: str) -> None:
        self._json = strategies_json

    async def complete(self, prompt: str, **kwargs) -> FakeLLMResponse:
        assert "estimated_savings" not in prompt or "Do NOT estimate" in prompt
        return FakeLLMResponse(text=self._json)


class MockTools:
    def __init__(self, scheme_limit: float = 150000, annual_income: float = 1200000) -> None:
        self.scheme_limit = scheme_limit
        self.annual_income = annual_income
        self.calls: list[tuple[str, dict]] = []

    def list_tools(self) -> list[str]:
        return ["get_user_profile", "get_scheme_details", "check_scheme_eligibility",
                "calculate_deduction_impact", "generate_tax_saving_alerts",
                "check_upcoming_deadlines", "save_analysis"]

    async def execute_tool(self, name: str, **kwargs) -> dict[str, Any]:
        self.calls.append((name, kwargs))
        if name == "get_user_profile":
            return {"success": True, "result": {"financial_profile": {"annual_income": self.annual_income}}}
        if name == "get_scheme_details":
            return {"success": True, "result": {"details": {"limit": self.scheme_limit}}}
        if name == "check_scheme_eligibility":
            return {"success": True, "result": {"eligible": True}}
        if name == "calculate_deduction_impact":
            result = TaxCalculationEngine.calculate_deduction_benefit(
                deduction_amount=kwargs["deduction_amount"],
                current_taxable_income=kwargs["current_taxable_income"],
                regime="old",
            )
            return {"success": True, "result": result}
        if name == "generate_tax_saving_alerts":
            return {"success": True, "result": {"alerts": []}}
        if name == "check_upcoming_deadlines":
            return {"success": True, "result": {"deadlines": []}}
        if name == "save_analysis":
            return {"success": True, "result": {}}
        return {"success": False, "error": f"unmocked tool {name}"}


STRATEGY_WITH_A_SMUGGLED_FIGURE = """{
  "strategies": [
    {
      "name": "Section 80C investments",
      "description": "Invest in ELSS/PPF",
      "estimated_savings": 999999,
      "difficulty": "Easy",
      "risk": "Low",
      "timeline": "Before year-end",
      "action": "Invest",
      "scheme_code": "80C"
    }
  ]
}"""


@pytest.mark.asyncio
async def test_llm_supplied_savings_figure_is_discarded_not_trusted(monkeypatch):
    monkeypatch.setattr(
        "backend.agents.tax_optimizer.get_llm",
        lambda: FakeLLM(STRATEGY_WITH_A_SMUGGLED_FIGURE),
    )
    agent = TaxOptimizerAgent()
    tools = MockTools(scheme_limit=150000, annual_income=1200000)

    output = await agent.execute("How do I save tax?", {"user_id": "u1"}, tools=tools)

    assert output.status == "success"
    strategy = output.result["strategies"][0]
    assert strategy["savings"] != 999999
    expected = TaxCalculationEngine.calculate_deduction_benefit(
        deduction_amount=150000, current_taxable_income=1200000, regime="old",
    )
    assert strategy["savings"] == float(expected["tax_savings"])


STRATEGY_WITH_NO_SCHEME_CODE = """{
  "strategies": [
    {
      "name": "Home office deduction",
      "description": "Claim a share of rent",
      "difficulty": "Medium",
      "risk": "Low",
      "timeline": "Next year",
      "action": "Keep receipts",
      "scheme_code": null
    }
  ]
}"""


@pytest.mark.asyncio
async def test_a_strategy_with_no_statutory_limit_gets_no_savings_figure(monkeypatch):
    """No scheme_code means no deterministic amount to test — the honest
    answer is 'not yet known', not a guess in either direction."""
    monkeypatch.setattr(
        "backend.agents.tax_optimizer.get_llm",
        lambda: FakeLLM(STRATEGY_WITH_NO_SCHEME_CODE),
    )
    agent = TaxOptimizerAgent()
    tools = MockTools()

    output = await agent.execute("What about my home office?", {"user_id": "u1"}, tools=tools)

    strategy = output.result["strategies"][0]
    assert strategy["savings"] is None
    assert "Home office deduction" in output.result["savings_not_yet_determinable"]
