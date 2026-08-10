"""RequestContext — AGT-003.

What this replaces
------------------
v1 threaded four separate pieces of global mutable state through the request
path:

    db_session_var      a module-level ContextVar holding the DB session
    AsyncSessionProxy   a proxy that read that ContextVar on every attribute
    OrchestratorProxy   a proxy that reached for a module-level orchestrator
    tool_executor       a module global, populated during app lifespan

Three consequences, and the third is a live bug:

  1. Agents could not be unit-tested without booting the whole lifespan.
  2. Two replicas behind a load balancer share none of it, so anything that
     looked like state was per-process by accident rather than design.
  3. **Scheduled jobs have no request context.** APScheduler calls a function
     on a background thread; `db_session_var` is unset there, so
     `AsyncSessionProxy.__getattr__` raises `RuntimeError: No active database
     session in this context`. The monthly health-report job cannot have worked.

The fix is not clever: pass the thing you need as an argument. A context is
constructed per request (or per job), carries what that unit of work needs, and
goes out of scope when it finishes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from backend.core.rules import TaxRuleset


@dataclass(slots=True)
class RequestContext:
    """Everything one unit of work needs, passed explicitly.

    Construct it at the edge — an HTTP handler, a scheduled job, a test — and
    thread it down. Nothing reads it from a global.
    """

    db: Any | None = None
    user_id: str | None = None
    fy: str | None = None
    tools: Any | None = None
    llm: Any | None = None
    correlation_id: str | None = None
    today: date = field(default_factory=date.today)

    # ── convenience ─────────────────────────────────────────────────────────

    def require_db(self) -> Any:
        """The DB session, or a message that says what to do about it.

        v1's equivalent raised `No active database session in this context`,
        which is true and unhelpful — it does not say that the caller was a
        background job that never had one.
        """
        if self.db is None:
            raise RuntimeError(
                "This operation needs a database session, and the RequestContext "
                "was built without one. If you are calling from a scheduled job, "
                "open a session with `job_context()` rather than relying on "
                "request-scoped state."
            )
        return self.db

    def require_fy(self) -> str:
        """The financial year, stated rather than assumed.

        There is deliberately no fallback to "current". A background job that
        forgets to set the year should fail, not silently compute the wrong one
        — which is precisely how v1 kept producing FY 2023-24 figures.
        """
        if not self.fy:
            raise RuntimeError(
                "No financial year in this context. State it explicitly: the "
                "engine has no default year, because revised returns and ITR-U "
                "need prior years to stay computable."
            )
        return self.fy

    def ruleset(self) -> TaxRuleset:
        from backend.core.rules import load_ruleset

        return load_ruleset(self.require_fy())

    def resolve_fy(self) -> str:
        """Fill in the financial year from `today` where the caller genuinely
        means 'as of now'. Explicit, and never implicit."""
        if not self.fy:
            from backend.core.rules import fy_for_date

            self.fy = fy_for_date(self.today)
        return self.fy

    def child(self, **overrides: Any) -> RequestContext:
        """A derived context — e.g. the same request against a different year."""
        base = {
            "db": self.db,
            "user_id": self.user_id,
            "fy": self.fy,
            "tools": self.tools,
            "llm": self.llm,
            "correlation_id": self.correlation_id,
            "today": self.today,
        }
        base.update(overrides)
        return RequestContext(**base)


# ── construction at the edges ───────────────────────────────────────────────

async def request_context(
    request: Any,
    db: Any,
    user: Any | None = None,
    *,
    fy: str | None = None,
) -> RequestContext:
    """Build a context for an HTTP request.

    Wire this as a FastAPI dependency so handlers receive a context instead of
    reaching into module state.
    """
    from backend.llm import get_llm, is_configured

    return RequestContext(
        db=db,
        user_id=getattr(user, "id", None),
        fy=fy,
        llm=get_llm() if is_configured() else None,
        correlation_id=getattr(getattr(request, "state", None), "correlation_id", None),
    )


class job_context:
    """A context for a scheduled job, with its own database session.

    This is the piece v1 was missing. APScheduler runs jobs on a background
    thread with no request in flight, so anything reading request-scoped state
    raised. A job opens its own session, uses it, and closes it.

        async with job_context(fy="2026-27") as ctx:
            await send_monthly_health_reports(ctx)
    """

    def __init__(self, *, fy: str | None = None, user_id: str | None = None) -> None:
        self._fy = fy
        self._user_id = user_id
        self._session_cm: Any | None = None
        self.ctx: RequestContext | None = None

    async def __aenter__(self) -> RequestContext:
        from backend.db.postgres import get_session_maker
        from backend.llm import get_llm, is_configured

        maker = await get_session_maker()
        self._session_cm = maker()
        session = await self._session_cm.__aenter__()

        self.ctx = RequestContext(
            db=session,
            user_id=self._user_id,
            fy=self._fy,
            llm=get_llm() if is_configured() else None,
            correlation_id="scheduled-job",
        )
        return self.ctx

    async def __aexit__(self, *exc: Any) -> None:
        if self._session_cm is not None:
            await self._session_cm.__aexit__(*exc)


def test_context(**overrides: Any) -> RequestContext:
    """A context for tests. No lifespan, no globals, no database unless asked.

    Its existence is the point of the refactor: an agent should be testable
    with three lines and no application boot.
    """
    defaults: dict[str, Any] = {
        "fy": "2026-27",
        "user_id": "test-user",
        "today": date(2026, 8, 9),
    }
    defaults.update(overrides)
    return RequestContext(**defaults)
