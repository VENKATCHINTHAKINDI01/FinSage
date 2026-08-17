"""Cost inflation indexation — PRC-008.

This file used to be twice as long and most of what came out was not replaced.

What was here, and why each piece had to go
-------------------------------------------
**A hardcoded Cost Inflation Index table**, ending at FY 2024-25 and falling
back to `254` or `363` for anything it did not have. A FY 2025-26 acquisition
was therefore indexed against 2015-16 with nothing raised. The table now lives
in the rule pack, where the loader raises for a year it does not cover — the
same discipline as every other rate in the product.

**A post-tax yield comparison across FDs, ELSS, gold, SGBs and debt funds.**
Every number in it was invented: FD at 7.5%, ELSS at 12%, gold at 6%, all
hardcoded floats presented to the user as though they were computed. It also
applied a 10% LTCG rate to ELSS, which has been 12.5% since 23 July 2024, and
ignored the ₹1,25,000 annual exemption while naming it in the label.

And it **recommended buying Sovereign Gold Bonds**, whose primary issuance the
government stopped in February 2024. A user acting on that advice would find
there is nothing to buy.

Deleting it rather than fixing it
----------------------------------
The rates could be corrected. The recommendation could be caveated. Neither is
the problem. Ranking investment products by projected post-tax return, for a
named individual, IS personalised investment advice — SEBI-regulated, and
outside what this product may do. AGT-006 already refuses it when a user asks;
it made no sense to keep a code path that volunteered it.

So the yield branch is gone and the agent says why, which is more useful to a
user than a comparison built on made-up returns.

What is left
-------------
Indexation, routed through the tool layer to the core engine, plus an
explanation. The agent does no arithmetic — it did seven separate calculations
before, including deriving a marginal slab rate from a hardcoded income ladder
that no longer matched the slabs.

Indexation still matters despite being abolished: a resident individual or HUF
selling immovable property acquired BEFORE 23 July 2024 may elect 20% with
indexation instead of 12.5% without, and will be able to for decades.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from backend.agents.base_agent import AgentOutput, TaxAgent, derive_confidence

logger = logging.getLogger(__name__)

# Kept as prose, not as a refusal pattern — AGT-006 owns the blocking check.
# This is the explanation the user gets instead of the comparison.
OUT_OF_SCOPE = (
    "Ranking investment products by expected return is personalised investment "
    "advice, which is SEBI-regulated and outside what this product does. What "
    "it can tell you is the TAX treatment of each — the rate, the holding "
    "period, the exemption and the section — and it will do that for any "
    "instrument you name. What it will not do is tell you which to buy, or put "
    "a projected return beside it."
)

SGB_POSITION = (
    "Sovereign Gold Bonds: the government has issued no new tranche since "
    "February 2024 and has announced no issuance calendar, so there is nothing "
    "to buy at primary issue. Existing bonds remain valid and are tradable on "
    "NSE and BSE, where they trade at a market price rather than the issue "
    "price. An earlier version of this product recommended buying them."
)


class PriceIntelligenceAgent(TaxAgent):
    """Cost inflation indexation, and an honest refusal about yields.

    The agent explains; the tool layer computes. There is no arithmetic in this
    class, which is what makes the `numeric_provenance` gate meaningful for it.
    """

    def __init__(self) -> None:
        super().__init__("price_intelligence_agent", "price_intelligence")

    async def execute(
        self,
        user_query: str,
        user_context: dict[str, Any],
        tools: Any = None,
        **kwargs: Any,
    ) -> AgentOutput:
        started = time.time()
        if tools is not None:
            self.set_tools(tools)

        query = (user_query or "").lower()
        wants_yields = any(
            term in query
            for term in ("yield", "return", "which is better", "compare "
                         "investment", "best investment", "sgb", "gold bond")
        )

        if wants_yields:
            return self._create_output(
                result={
                    "calculation_type": "declined_out_of_scope",
                    "explanation": OUT_OF_SCOPE,
                    "sovereign_gold_bonds": SGB_POSITION,
                    "what_this_can_do": [
                        "The tax treatment of any instrument you name — rate, "
                        "holding period, exemption and section.",
                        "Cost inflation indexation for property acquired "
                        "before 23 July 2024.",
                        "The tax on a specific disposal you have actually "
                        "made or are about to make.",
                    ],
                    "recommendations": [OUT_OF_SCOPE],
                },
                status="declined",
                confidence=derive_confidence(used_llm_for_values=False),
                reasoning=(
                    "Declined: a post-tax yield ranking is personalised "
                    "investment advice."
                ),
                execution_time_ms=(time.time() - started) * 1000,
            )

        return await self._indexation(user_context, started)

    async def _indexation(
        self, user_context: dict[str, Any], started: float,
    ) -> AgentOutput:
        """Route to the engine. Every figure below comes back from a tool."""
        missing = [
            name for name in ("acquired_on", "sold_on", "cost", "consideration")
            if not user_context.get(name)
        ]
        if missing:
            return self._create_output(
                result={
                    "calculation_type": "insufficient_data",
                    "missing_fields": missing,
                    "explanation": (
                        "A capital gain cannot be computed without "
                        + ", ".join(missing)
                        + ". These are not fields to estimate — the date of "
                        "acquisition alone decides whether the 20%-with-"
                        "indexation election is available at all."
                    ),
                    "recommendations": [],
                },
                status="needs_input",
                confidence=derive_confidence(missing_inputs=missing),
                reasoning="Missing inputs for a capital gains computation.",
                execution_time_ms=(time.time() - started) * 1000,
            )

        if not self.tools:
            return self._create_output(
                result={
                    "calculation_type": "unavailable",
                    "explanation": (
                        "The capital gains engine is not reachable, and this "
                        "agent does not compute figures itself."
                    ),
                    "recommendations": [],
                },
                status="error",
                confidence=derive_confidence(error="no tools"),
                reasoning="Tool layer unavailable.",
                execution_time_ms=(time.time() - started) * 1000,
            )

        response = await self.call_tool(
            "calculate_capital_gains",
            disposals=[{
                "asset": user_context.get("asset", "immovable_property"),
                "acquired_on": str(user_context["acquired_on"]),
                "sold_on": str(user_context["sold_on"]),
                "cost": user_context["cost"],
                "consideration": user_context["consideration"],
                "improvement_cost": user_context.get("improvement_cost", 0),
                "transfer_expenses": user_context.get("transfer_expenses", 0),
            }],
            fy=user_context.get("fy"),
        )

        if not response.get("success"):
            return self._create_output(
                result={
                    "calculation_type": "unavailable",
                    "explanation": response.get("error", "The engine declined."),
                    "recommendations": [],
                },
                status="error",
                confidence=derive_confidence(error=response.get("error")),
                reasoning="The capital gains engine declined the disposal.",
                execution_time_ms=(time.time() - started) * 1000,
            )

        result = dict(response.get("result") or response)
        result["calculation_type"] = "capital_gains"
        result["recommendations"] = [
            "Indexation was abolished for transfers on or after 23 July 2024. "
            "It survives as an ELECTION for a resident individual or HUF "
            "selling immovable property acquired before that date, who may "
            "choose 20% with indexation over 12.5% without — whichever is "
            "lower for them.",
        ]
        return self._create_output(
            result=result,
            confidence=derive_confidence(
                tool_results=[response], used_llm_for_values=False,
            ),
            reasoning="Capital gains computed by the core engine.",
            execution_time_ms=(time.time() - started) * 1000,
        )
