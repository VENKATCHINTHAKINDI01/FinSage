"""Shared types for the eval harness.

Deliberately dependency-free so scorers can be unit-tested without booting the
application or reaching a model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


# str+Enum rather than StrEnum: identical behaviour here, but it keeps the
# harness importable on 3.10 so the phase gate can be run in environments
# other than the one CI happens to use. A gate you can only run in CI is a
# gate you stop running.
class Verdict(str, Enum):
    PASS = "pass"  # noqa: S105 — a verdict, not a credential
    FAIL = "fail"
    # The scenario could not be judged: a missing fixture, or a scorer that
    # does not apply. Distinct from FAIL on purpose, because a harness that
    # could not run must never be mistaken for one that ran and approved.
    SKIP = "skip"


@dataclass(frozen=True)
class Score:
    """One scorer's judgement of one scenario."""

    scorer: str
    verdict: Verdict
    value: float | None = None          # 0.0–1.0 where the scorer is graded
    detail: str = ""
    evidence: list[str] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return self.verdict is Verdict.FAIL


@dataclass
class AgentInvocation:
    """Everything one agent run saw and produced.

    `tool_results` is the ground truth the agent was given. numeric_provenance
    checks the agent's prose against it — which is why it must be captured
    verbatim, not summarised.
    """

    agent: str
    query: str
    profile: dict[str, Any]
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    output_text: str = ""
    output_data: dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error: str | None = None


@dataclass
class ScenarioResult:
    scenario_id: str
    invocation: AgentInvocation
    scores: list[Score] = field(default_factory=list)

    @property
    def verdict(self) -> Verdict:
        if any(s.failed for s in self.scores):
            return Verdict.FAIL
        if not self.scores or all(s.verdict is Verdict.SKIP for s in self.scores):
            return Verdict.SKIP
        return Verdict.PASS

    @property
    def failures(self) -> list[Score]:
        return [s for s in self.scores if s.failed]


@dataclass
class EvalOutcome:
    """Result of a full suite run, comparable against baseline.json."""

    results: list[ScenarioResult] = field(default_factory=list)
    mode: str = "replay"                # replay | live

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.verdict is Verdict.PASS)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.verdict is Verdict.FAIL)

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.verdict is Verdict.SKIP)

    def summary(self) -> dict[str, Any]:
        """Stable shape for baseline comparison. Keys sorted; no timestamps,
        so a clean run diffs to nothing."""
        return {
            "mode": self.mode,
            "total": len(self.results),
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "scenarios": {
                r.scenario_id: {
                    "verdict": r.verdict.value,
                    "scorers": {
                        s.scorer: s.verdict.value
                        for s in sorted(r.scores, key=lambda x: x.scorer)
                    },
                }
                for r in sorted(self.results, key=lambda x: x.scenario_id)
            },
        }


class Scorer(Protocol):
    """Plugin interface. A scorer judges one invocation against one scenario.

    Scorers must be pure: no network, no model calls. A scorer that needed a
    model to decide would be exactly the thing this harness exists to police.
    """

    name: str

    def score(
        self,
        scenario: dict[str, Any],
        invocation: AgentInvocation,
    ) -> Score: ...
