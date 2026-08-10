"""Parallel agent execution — AGT-002.

v1 ran agents in a `for` loop, each making one or more blocking LLM calls.
Latency was the sum of every agent's, and a single agent raising took the whole
response with it.

Three changes:

  **Concurrency.** Independent agents run under `asyncio.gather`. Latency
  becomes the slowest agent rather than the total, which for a two-agent intent
  roughly halves it.

  **Per-agent timeouts.** One agent hanging must not hold the response open.
  A timeout is recorded as that agent failing, not as the request failing.

  **Partial-failure tolerance.** If three agents run and one raises, the user
  gets the two that worked, plus an explicit note about the one that did not.
  v1 returned an error dict inside `results` that callers then treated as a
  successful result — the failure was recorded and then quietly ignored.

What is NOT here: an agent that depends on another agent's output. Nothing in
the current intent map does, and inventing a dependency graph for a
dependency-free workload is how you end up with LangGraph in the requirements
and a for-loop in the code.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 20.0


@dataclass(slots=True)
class AgentRun:
    """One agent's outcome. A failure is a first-class result, not an absence."""

    name: str
    ok: bool
    result: Any = None
    error: str | None = None
    timed_out: bool = False
    latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.name,
            "ok": self.ok,
            "error": self.error,
            "timed_out": self.timed_out,
            "latency_ms": round(self.latency_ms, 1),
        }


@dataclass(slots=True)
class FanOutResult:
    runs: list[AgentRun] = field(default_factory=list)
    wall_ms: float = 0.0

    @property
    def succeeded(self) -> list[AgentRun]:
        return [r for r in self.runs if r.ok]

    @property
    def failed(self) -> list[AgentRun]:
        return [r for r in self.runs if not r.ok]

    @property
    def all_failed(self) -> bool:
        return bool(self.runs) and not self.succeeded

    @property
    def sequential_ms(self) -> float:
        """What a for-loop would have cost. Reported so the speedup is visible
        rather than asserted."""
        return sum(r.latency_ms for r in self.runs)

    def user_facing_notes(self) -> list[str]:
        """What to tell the user about the agents that did not finish.

        Named rather than silent: "we could not check X" is information. v1
        stored the error and rendered nothing.
        """
        notes = []
        for r in self.failed:
            if r.timed_out:
                notes.append(f"The {r.name.replace('_', ' ')} check timed out and is not included below.")
            else:
                notes.append(f"The {r.name.replace('_', ' ')} check could not run and is not included below.")
        return notes

    def to_dict(self) -> dict[str, Any]:
        return {
            "runs": [r.to_dict() for r in self.runs],
            "wall_ms": round(self.wall_ms, 1),
            "sequential_ms": round(self.sequential_ms, 1),
            "succeeded": len(self.succeeded),
            "failed": len(self.failed),
        }


async def _run_one(
    name: str,
    coro_factory: Any,
    timeout_s: float,
) -> AgentRun:
    started = time.perf_counter()
    try:
        result = await asyncio.wait_for(coro_factory(), timeout=timeout_s)
    # Both, deliberately. `asyncio.TimeoutError` became an alias of the builtin
    # `TimeoutError` in 3.11, so on the declared target they are one class and
    # this is harmless. On 3.10 they are NOT, and catching only the builtin
    # sends every timeout to the generic handler below — losing the
    # `timed_out` flag and telling the user an agent "could not run" when it
    # actually hung. A ruff autofix introduced exactly that, and only the
    # timeout tests caught it.
    except (TimeoutError, asyncio.TimeoutError):  # noqa: UP041
        elapsed = (time.perf_counter() - started) * 1000
        logger.warning("agent %s timed out after %.1fs", name, timeout_s)
        return AgentRun(name, ok=False, error=f"timed out after {timeout_s}s",
                        timed_out=True, latency_ms=elapsed)
    except Exception as exc:
        elapsed = (time.perf_counter() - started) * 1000
        logger.exception("agent %s failed", name)
        return AgentRun(name, ok=False, error=str(exc), latency_ms=elapsed)

    return AgentRun(name, ok=True, result=result,
                    latency_ms=(time.perf_counter() - started) * 1000)


async def fan_out(
    agents: dict[str, Any],
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> FanOutResult:
    """Run independent agents concurrently.

    `agents` maps a name to a zero-argument callable returning a coroutine —
    a factory rather than a coroutine, so nothing starts until we gather and
    an unused entry cannot leak a never-awaited warning.
    """
    if not agents:
        return FanOutResult()

    started = time.perf_counter()
    runs = await asyncio.gather(
        *(_run_one(name, factory, timeout_s) for name, factory in agents.items())
    )
    return FanOutResult(runs=list(runs), wall_ms=(time.perf_counter() - started) * 1000)
