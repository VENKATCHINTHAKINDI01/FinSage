"""RequestContext and parallel fan-out — AGT-003, AGT-002.

The context tests exist because v1's global state hid a live bug: scheduled
jobs could not reach a database session, so the monthly health-report job
raised on every run. The parallel tests exist because a for-loop over agents
made latency additive and one failure fatal.
"""

from __future__ import annotations

import asyncio
from datetime import date

import pytest

from backend.context import RequestContext, test_context
from backend.orchestrator.parallel import fan_out

# ═══ RequestContext — AGT-003 ═══════════════════════════════════════════════

class TestNoImplicitState:
    def test_a_context_needs_no_lifespan_or_globals(self) -> None:
        """The point of the refactor: three lines, no application boot."""
        ctx = test_context()
        assert ctx.fy == "2026-27"
        assert ctx.user_id == "test-user"
        assert ctx.db is None

    def test_missing_db_explains_the_scheduled_job_case(self) -> None:
        """v1 raised 'No active database session in this context', which is
        true and tells a background-job author nothing."""
        with pytest.raises(RuntimeError, match="job_context"):
            test_context().require_db()

    def test_missing_financial_year_raises_rather_than_defaulting(self) -> None:
        """A job that forgets the year should fail, not silently compute the
        wrong one — which is exactly how v1 kept producing FY 2023-24."""
        with pytest.raises(RuntimeError, match="no default year"):
            RequestContext().require_fy()

    def test_resolve_fy_is_explicit_opt_in(self) -> None:
        assert RequestContext(today=date(2026, 8, 9)).resolve_fy() == "2026-27"
        assert RequestContext(today=date(2026, 2, 14)).resolve_fy() == "2025-26"

    def test_resolve_does_not_override_a_stated_year(self) -> None:
        ctx = RequestContext(fy="2024-25", today=date(2026, 8, 9))
        assert ctx.resolve_fy() == "2024-25"

    def test_ruleset_comes_from_the_context_year(self) -> None:
        assert test_context().ruleset().fy == "2026-27"
        assert test_context(fy="2024-25").ruleset().fy == "2024-25"

    def test_child_inherits_and_overrides(self) -> None:
        parent = test_context(correlation_id="abc123")
        child = parent.child(fy="2025-26")
        assert child.fy == "2025-26"
        assert child.correlation_id == "abc123"
        assert parent.fy == "2026-27", "parent must not be mutated"

    def test_two_contexts_do_not_share_state(self) -> None:
        """The property a ContextVar could not give us across threads."""
        a, b = test_context(user_id="alice"), test_context(user_id="bob")
        a.fy = "2024-25"
        assert b.fy == "2026-27"
        assert (a.user_id, b.user_id) == ("alice", "bob")


# ═══ Parallel fan-out — AGT-002 ═════════════════════════════════════════════

def _slow(delay: float, value: str = "ok"):
    async def run():
        await asyncio.sleep(delay)
        return value
    return run


def _boom(message: str = "engine unavailable"):
    async def run():
        raise RuntimeError(message)
    return run


class TestConcurrency:
    async def test_agents_run_concurrently_not_sequentially(self) -> None:
        """Three 100ms agents should take ~100ms, not ~300ms."""
        result = await fan_out({
            "a": _slow(0.1), "b": _slow(0.1), "c": _slow(0.1),
        })
        assert len(result.succeeded) == 3
        assert result.wall_ms < 250, f"looks sequential: {result.wall_ms:.0f}ms"
        assert result.sequential_ms > result.wall_ms

    async def test_empty_input_is_not_an_error(self) -> None:
        result = await fan_out({})
        assert result.runs == [] and result.wall_ms == 0.0


class TestPartialFailure:
    async def test_one_failure_does_not_lose_the_others(self) -> None:
        """v1 stored the error inside `results` and callers treated it as a
        successful result."""
        result = await fan_out({
            "deduction_hunter": _slow(0.01, "found 3"),
            "compliance_checker": _boom(),
            "itr_helper": _slow(0.01, "ITR-1"),
        })
        assert len(result.succeeded) == 2
        assert len(result.failed) == 1
        assert result.failed[0].name == "compliance_checker"
        assert not result.all_failed

    async def test_a_failure_is_named_to_the_user_not_swallowed(self) -> None:
        result = await fan_out({"ok": _slow(0.01), "compliance_checker": _boom()})
        notes = result.user_facing_notes()
        assert len(notes) == 1
        assert "compliance checker" in notes[0]
        assert "not included" in notes[0]

    async def test_total_failure_is_distinguishable(self) -> None:
        """All agents failing must not read the same as all agents returning
        nothing to say."""
        result = await fan_out({"a": _boom(), "b": _boom()})
        assert result.all_failed
        assert result.succeeded == []

    async def test_the_error_message_is_preserved_for_logs(self) -> None:
        result = await fan_out({"a": _boom("qdrant unreachable")})
        assert "qdrant unreachable" in result.failed[0].error


class TestTimeouts:
    async def test_a_hanging_agent_does_not_hold_the_response(self) -> None:
        result = await fan_out(
            {"fast": _slow(0.01), "hung": _slow(5.0)}, timeout_s=0.1
        )
        assert len(result.succeeded) == 1
        assert result.failed[0].timed_out
        assert result.wall_ms < 500

    async def test_a_timeout_reads_differently_from_a_crash(self) -> None:
        result = await fan_out({"slow": _slow(5.0)}, timeout_s=0.05)
        note = result.user_facing_notes()[0]
        assert "timed out" in note

    async def test_latency_is_recorded_per_agent(self) -> None:
        result = await fan_out({"a": _slow(0.05), "b": _slow(0.01)})
        by_name = {r.name: r for r in result.runs}
        assert by_name["a"].latency_ms > by_name["b"].latency_ms


async def test_serialises_with_the_speedup_visible() -> None:
    """The comparison is reported rather than asserted in a comment, so a
    regression to sequential execution shows up in the payload."""
    d = (await fan_out({"a": _slow(0.05), "b": _slow(0.05)})).to_dict()
    assert d["succeeded"] == 2
    assert d["sequential_ms"] > d["wall_ms"]
