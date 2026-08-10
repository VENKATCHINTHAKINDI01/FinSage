"""
Agent evaluation harness.

Layer 3 of the four-layer test strategy (see docs/IMPLEMENTATION_PLAN.md §3).

    Layer 1  golden tax tests      backend/core/tests/golden/     deterministic
    Layer 2  property invariants   backend/core/tests/properties/ deterministic
    Layer 3  agent evals           backend/evals/                 LLM in the loop
    Layer 4  contract & load       tests/contract/, tests/load/

Why this layer exists
---------------------
Layers 1 and 2 prove the arithmetic is right. They say nothing about whether an
agent faithfully reported that arithmetic to the user. Layer 3 closes that gap.

The keystone is `scorers/numeric_provenance.py`: it extracts every number from
an agent's user-facing output and fails if the number does not appear in the
tool results the agent received. That makes the project's governing rule —

    No rupee figure shown to a user may originate from a language model.

— mechanical rather than cultural. You cannot merge a hallucinated amount.

Determinism
-----------
CI replays recorded LLM responses from `fixtures/`, so the suite is fast, free
and reproducible. A nightly job runs the same scenarios live against the model
to catch drift, and updates `baseline.json` only on explicit human acceptance.
"""

from backend.evals.types import (
    EvalOutcome,
    ScenarioResult,
    Score,
    Scorer,
    Verdict,
)

__all__ = ["EvalOutcome", "ScenarioResult", "Score", "Scorer", "Verdict"]
