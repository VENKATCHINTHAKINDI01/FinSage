"""The live orchestrator runs agents concurrently — AGT-002.

`backend/orchestrator/parallel.py` was fully tested and CALLED BY NOTHING: the
/chat/query path used a sequential for-loop while AGT-002 was recorded as
having concurrency. These tests are against `AgentOrchestrator`, the
class that actually serves traffic, so the criterion cannot go back to being
true only in an uncalled module.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from backend.orchestrator.graph import AgentOrchestrator


class SlowAgent:
    """Sleeps, so wall-clock tells sequential from concurrent."""

    def __init__(self, delay: float = 0.2, fail: bool = False, hang: bool = False):
        self.delay, self.fail, self.hang = delay, fail, hang

    async def execute(self, **kwargs):
        if self.hang:
            await asyncio.sleep(60)
        await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError("this agent exploded")
        return {"status": "success", "confidence": 0.9, "result": {}}


def orchestrator(**agents) -> AgentOrchestrator:
    o = AgentOrchestrator.__new__(AgentOrchestrator)
    o.agents = agents
    o.tools = None
    return o


@pytest.mark.asyncio
async def test_four_agents_take_one_agents_time_not_four():
    """The whole point. Sequentially this is 0.8s; concurrently it is 0.2s."""
    o = orchestrator(**{f"a{i}": SlowAgent(0.2) for i in range(4)})

    started = time.perf_counter()
    out = await o.orchestrate("q", "u-1", {}, agents_to_invoke=list(o.agents))
    elapsed = time.perf_counter() - started

    assert elapsed < 0.6, f"took {elapsed:.2f}s — that is sequential"
    assert len(out["agent_results"]) == 4


@pytest.mark.asyncio
async def test_one_agent_failing_does_not_fail_the_response():
    o = orchestrator(good=SlowAgent(0.01), bad=SlowAgent(0.01, fail=True))
    out = await o.orchestrate("q", "u-1", {}, agents_to_invoke=["good", "bad"])

    statuses = {e["agent"]: e["status"] for e in out["execution_log"]}
    assert statuses["good"] == "success"
    assert statuses["bad"] == "error"
    assert out["agent_results"]["good"]["status"] == "success"


@pytest.mark.asyncio
async def test_a_hanging_agent_is_reported_as_a_timeout_not_a_generic_error():
    """The two need different things from whoever reads the log: an error is a
    bug to fix, a timeout is a dependency to chase."""
    o = orchestrator(fast=SlowAgent(0.01), stuck=SlowAgent(hang=True))
    from backend.orchestrator import parallel

    original = parallel.DEFAULT_TIMEOUT_S
    parallel.DEFAULT_TIMEOUT_S = 0.2
    try:
        out = await o.orchestrate("q", "u-1", {}, agents_to_invoke=["fast", "stuck"])
    finally:
        parallel.DEFAULT_TIMEOUT_S = original

    statuses = {e["agent"]: e["status"] for e in out["execution_log"]}
    assert statuses["fast"] == "success"
    assert statuses["stuck"] == "timeout"


@pytest.mark.asyncio
async def test_an_unknown_agent_is_skipped_and_logged_not_crashed():
    o = orchestrator(real=SlowAgent(0.01))
    out = await o.orchestrate("q", "u-1", {}, agents_to_invoke=["real", "ghost"])
    assert set(out["agent_results"]) == {"real"}


@pytest.mark.asyncio
async def test_every_agent_reports_its_own_latency():
    """A single wall-clock number cannot tell you which agent was slow."""
    o = orchestrator(quick=SlowAgent(0.01), slower=SlowAgent(0.25))
    out = await o.orchestrate("q", "u-1", {}, agents_to_invoke=["quick", "slower"])
    times = {e["agent"]: e["time_ms"] for e in out["execution_log"]}
    assert times["slower"] > times["quick"]
