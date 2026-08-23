"""Eval suite runner.

    python -m backend.evals.runner                 # replay from fixtures
    python -m backend.evals.runner --live          # call the real model
    python -m backend.evals.runner --update-baseline

Replay is the default and is what CI uses: deterministic, offline, free. The
live path exists to catch model drift and runs nightly; its results are only
written to the baseline on explicit human acceptance.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from backend.evals.scorers import REGISTRY
from backend.evals.types import (
    AgentInvocation,
    EvalOutcome,
    ScenarioResult,
    Score,
    Verdict,
)

logger = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent
SCENARIOS = HERE / "scenarios"
FIXTURES = HERE / "fixtures"
BASELINE = HERE / "baseline.json"


# ── Loading ─────────────────────────────────────────────────────────────────

def _load_structured(path: Path) -> Any:
    """Read YAML if available, else JSON. Keeps the harness runnable in a bare
    environment; CI has PyYAML so scenarios can stay in YAML."""
    text = path.read_text(encoding="utf-8")
    if path.suffix in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                f"{path.name} is YAML but PyYAML is not installed"
            ) from exc
        return yaml.safe_load(text)
    return json.loads(text)


def load_scenarios(only: str | None = None) -> list[dict[str, Any]]:
    if not SCENARIOS.exists():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(SCENARIOS.rglob("*")):
        if path.suffix not in {".yaml", ".yml", ".json"}:
            continue
        data = _load_structured(path)
        for item in data if isinstance(data, list) else [data]:
            if not item:
                continue
            item.setdefault("id", path.stem)
            if only and only not in item["id"]:
                continue
            out.append(item)
    return out


def load_fixture(scenario_id: str) -> AgentInvocation | None:
    """A recorded invocation: what the agent saw, and what it said."""
    for suffix in (".json", ".yaml", ".yml"):
        path = FIXTURES / f"{scenario_id}{suffix}"
        if path.exists():
            raw = _load_structured(path)
            return AgentInvocation(
                agent=raw.get("agent", "unknown"),
                query=raw.get("query", ""),
                profile=raw.get("profile", {}),
                tool_calls=raw.get("tool_calls", []),
                tool_results=raw.get("tool_results", []),
                output_text=raw.get("output_text", ""),
                output_data=raw.get("output_data", {}),
                latency_ms=raw.get("latency_ms", 0.0),
                prompt_tokens=raw.get("prompt_tokens", 0),
                completion_tokens=raw.get("completion_tokens", 0),
                error=raw.get("error"),
            )
    return None


# ── Execution ───────────────────────────────────────────────────────────────

def invoke_live(scenario: dict[str, Any], **pipeline_kwargs: Any) -> AgentInvocation:
    """Run the REAL pipeline against a scenario and record what came back.

    Generic, which is the point. Three fixtures existed before this and each
    was made by a standalone script with hand-built tool results; that is why
    ten scenarios had none. The tool results now come from the scenario's own
    `tools:` declaration (see `backend.evals.toolcalls`), so any scenario can
    produce a fixture without new code.

    `pipeline_kwargs` exists so a test can inject a stub Analyst and Reviewer
    and exercise this path with no network — otherwise the only way to know
    the wiring works is to spend money finding out.
    """
    import asyncio
    import time

    from backend.agents import pipeline as agent_pipeline
    from backend.evals.toolcalls import results_for

    profile = dict(scenario.get("profile") or {})
    tool_results = results_for(scenario)

    started = time.perf_counter()
    result = asyncio.run(agent_pipeline.run(
        query=scenario.get("query", ""),
        profile=profile,
        fy=str(profile.get("fy", "2026-27")),
        regime=str(profile.get("regime", "new")),
        tool_results=tool_results,
        **pipeline_kwargs,
    ))
    elapsed = (time.perf_counter() - started) * 1000

    return AgentInvocation(
        agent="analyst_reviewer_pipeline",
        query=scenario.get("query", ""),
        profile=profile,
        tool_calls=[{"tool": t["tool"]} for t in tool_results],
        tool_results=tool_results,
        # `.answer` is a FinalAnswer, not a string. Recording the object
        # would give the scorers a repr to grade, and every figure in it
        # would look fabricated because the repr is not the answer.
        output_text=result.answer.text,
        output_data=result.to_dict() if hasattr(result, "to_dict") else {},
        latency_ms=elapsed,
    )


def save_fixture(scenario_id: str, invocation: AgentInvocation) -> Path:
    """Record an invocation so it replays offline forever after.

    Deliberately separate from `invoke_live`. A fixture is only worth keeping
    if it PASSED — recording a run in which the model fabricated a figure would
    freeze the fabrication into the suite as expected behaviour, which is how a
    regression corpus starts certifying bugs.
    """
    import json

    path = FIXTURES / f"{scenario_id}.json"
    path.write_text(json.dumps({
        "_comment": (
            "Recorded from a live model run and scored before saving. Regenerate "
            "with `python -m backend.evals.runner --live --record --only <id>`."
        ),
        "agent": invocation.agent,
        "query": invocation.query,
        "profile": invocation.profile,
        "tool_calls": invocation.tool_calls,
        "tool_results": invocation.tool_results,
        "output_text": invocation.output_text,
        "output_data": invocation.output_data,
        "latency_ms": invocation.latency_ms,
    }, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def run_scenario(
    scenario: dict[str, Any],
    live: bool,
    *,
    record: bool = False,
    **pipeline_kwargs: Any,
) -> ScenarioResult:
    sid = scenario["id"]

    if live:
        invocation = invoke_live(scenario, **pipeline_kwargs)
        scores = [s.score(scenario, invocation) for s in REGISTRY.values()]
        if record:
            # Only a clean run is worth freezing. See `save_fixture`.
            if any(s.verdict is Verdict.FAIL for s in scores):
                logger.warning(
                    "%s failed scoring; NOT recording a fixture. Freezing a run "
                    "the scorers rejected would make the failure the expected "
                    "behaviour.", sid,
                )
            else:
                save_fixture(sid, invocation)
        return ScenarioResult(scenario_id=sid, invocation=invocation, scores=scores)

    invocation = load_fixture(sid)
    if invocation is None:
        return ScenarioResult(
            scenario_id=sid,
            invocation=AgentInvocation(agent="?", query=scenario.get("query", ""),
                                       profile=scenario.get("profile", {})),
            scores=[Score("harness", Verdict.SKIP, detail="no recorded fixture")],
        )

    return ScenarioResult(
        scenario_id=sid,
        invocation=invocation,
        scores=[s.score(scenario, invocation) for s in REGISTRY.values()],
    )


def run(only: str | None = None, live: bool = False,
        record: bool = False) -> EvalOutcome:
    scenarios = load_scenarios(only)
    return EvalOutcome(
        results=[run_scenario(s, live, record=record) for s in scenarios],
        mode="live" if live else "replay",
    )


# ── Baseline ────────────────────────────────────────────────────────────────

def read_baseline() -> dict[str, Any] | None:
    if not BASELINE.exists():
        return None
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def write_baseline(outcome: EvalOutcome) -> None:
    BASELINE.write_text(
        json.dumps(outcome.summary(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def regressions(outcome: EvalOutcome, baseline: dict[str, Any]) -> list[str]:
    """Scenarios that used to pass and now do not.

    New scenarios failing is not a regression — it is work in progress. A
    previously passing scenario failing, or disappearing entirely, is.
    """
    was = baseline.get("scenarios", {})
    now = outcome.summary()["scenarios"]
    out: list[str] = []

    for sid, prev in sorted(was.items()):
        if prev.get("verdict") != Verdict.PASS.value:
            continue
        if sid not in now:
            out.append(f"{sid}: was passing, now missing from the suite")
        elif now[sid]["verdict"] != Verdict.PASS.value:
            failing = [
                name for name, v in now[sid]["scorers"].items()
                if v == Verdict.FAIL.value
            ]
            out.append(f"{sid}: was passing, now {now[sid]['verdict']}"
                       + (f" ({', '.join(failing)})" if failing else ""))
    return out


# ── Reporting ───────────────────────────────────────────────────────────────

_MARK = {Verdict.PASS: "PASS", Verdict.FAIL: "FAIL", Verdict.SKIP: "skip"}


def report(outcome: EvalOutcome) -> str:
    lines = [f"Agent evals — {outcome.mode} mode", ""]

    if not outcome.results:
        lines += ["  no scenarios yet (populated in AGT-005, phase 3)", ""]
        return "\n".join(lines)

    for r in sorted(outcome.results, key=lambda x: x.scenario_id):
        lines.append(f"  [{_MARK[r.verdict]}] {r.scenario_id}")
        for s in r.failures:
            lines.append(f"         {s.scorer}: {s.detail}")
            lines += [f"           · {e}" for e in s.evidence]

    lines += ["", f"  {outcome.passed} passed · {outcome.failed} failed "
                  f"· {outcome.skipped} skipped", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the agent eval suite")
    ap.add_argument("--only", help="substring filter on scenario id")
    ap.add_argument("--record", action="store_true",
                    help="save a fixture for each scenario that passes scoring")
    ap.add_argument("--live", action="store_true",
                    help="call the real model instead of replaying fixtures")
    ap.add_argument("--update-baseline", action="store_true",
                    help="accept current results as the new baseline")
    args = ap.parse_args()

    outcome = run(only=args.only, live=args.live, record=args.record)
    print(report(outcome))

    if args.update_baseline:
        write_baseline(outcome)
        print(f"baseline updated: {BASELINE.name}")
        return 0

    baseline = read_baseline()
    if baseline:
        regs = regressions(outcome, baseline)
        if regs:
            print("REGRESSIONS vs baseline:", file=sys.stderr)
            for r in regs:
                print(f"  ✗ {r}", file=sys.stderr)
            return 1

    # numeric_provenance is a hard gate at zero failures, always.
    provenance_failures = [
        r.scenario_id for r in outcome.results
        for s in r.scores
        if s.scorer == "numeric_provenance" and s.failed
    ]
    if provenance_failures:
        print(
            "numeric_provenance failures (hard gate — a model invented a "
            f"figure): {', '.join(provenance_failures)}",
            file=sys.stderr,
        )
        return 1

    return 1 if outcome.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
