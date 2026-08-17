"""Postgres-backed adapter for `backend.security.sessions.SessionStore` — PRD-002.

The rotation logic in `security/sessions.py` is deliberately pure and
synchronous, tested against `InMemorySessions`. SQLAlchemy's async session
cannot satisfy that sync protocol directly, so this module bridges the two:
load the rows a call will touch into an `InMemorySessions` snapshot, run the
pure function against it, then write back whatever changed.

A rotation touches at most one family (the presented token's), so the load is
always scoped to `family`, never the whole table. The one exception is the
revocation check on every authenticated request (`load_check_store`), which
is intentionally narrower still — it never loads a whole family, just the
one row and one EXISTS check the hot path actually needs.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.orm_models import RefreshSession
from backend.security.sessions import InMemorySessions, SessionRecord, State


def _to_record(row: RefreshSession) -> SessionRecord:
    return SessionRecord(
        jti=row.jti,
        family=row.family,
        user_id=row.user_id,
        issued_at=row.issued_at,
        expires_at=row.expires_at,
        state=State(row.state),
        replaced_by=row.replaced_by or "",
    )


async def load_family_store(db: AsyncSession, jti: str) -> InMemorySessions:
    """Snapshot of the family `jti` belongs to, ready for `rotate`/`logout`.

    If `jti` is unknown the store comes back empty — `rotate` raises
    `TokenRejected("unknown", ...)` against that, which is the correct
    behaviour for a forged or stale token.
    """
    store = InMemorySessions()
    row = await db.get(RefreshSession, jti)
    if row is None:
        return store

    result = await db.execute(
        select(RefreshSession).where(RefreshSession.family == row.family)
    )
    for member in result.scalars():
        record = _to_record(member)
        store.records[record.jti] = record
        if record.state is State.REVOKED:
            store.revoked_families.add(record.family)
    return store


async def persist_store(db: AsyncSession, store: InMemorySessions) -> None:
    """Write every record the snapshot holds back to its row, upserting."""
    for record in store.records.values():
        row = await db.get(RefreshSession, record.jti)
        if row is None:
            row = RefreshSession(jti=record.jti)
            db.add(row)
        row.family = record.family
        row.user_id = record.user_id
        row.issued_at = record.issued_at
        row.expires_at = record.expires_at
        row.state = record.state.value
        row.replaced_by = record.replaced_by or None
    await db.commit()


async def persist_new_record(db: AsyncSession, record: SessionRecord) -> None:
    """Fast path for `start_session`: exactly one new row, no snapshot needed."""
    db.add(RefreshSession(
        jti=record.jti,
        family=record.family,
        user_id=record.user_id,
        issued_at=record.issued_at,
        expires_at=record.expires_at,
        state=record.state.value,
        replaced_by=record.replaced_by or None,
    ))
    await db.commit()


class _CheckOnlyStore:
    """Read-only, pre-loaded answer to exactly what `assert_usable` asks.

    Satisfies `SessionStore` structurally so it can be passed to
    `assert_usable`, but `put` and `family_members` are stubs — the
    revocation check never calls either, and nothing here is written back.
    """

    def __init__(self, *, family_revoked: bool, record: SessionRecord | None) -> None:
        self._family_revoked = family_revoked
        self._record = record

    def get(self, jti: str) -> SessionRecord | None:
        if self._record is not None and self._record.jti == jti:
            return self._record
        return None

    def put(self, record: SessionRecord) -> None:
        raise NotImplementedError("_CheckOnlyStore is read-only")

    def family_members(self, family: str) -> list[SessionRecord]:
        return [self._record] if self._record is not None else []

    def is_family_revoked(self, family: str) -> bool:
        return self._family_revoked


async def load_check_store(
    db: AsyncSession, *, family: str, jti: str | None,
) -> _CheckOnlyStore:
    """The two lightweight, indexed lookups `assert_usable` needs per request."""
    revoked_stmt = select(RefreshSession.jti).where(
        RefreshSession.family == family, RefreshSession.state == State.REVOKED.value,
    ).limit(1)
    family_revoked = (await db.execute(revoked_stmt)).first() is not None

    record: SessionRecord | None = None
    if jti:
        row = await db.get(RefreshSession, jti)
        if row is not None:
            record = _to_record(row)

    return _CheckOnlyStore(family_revoked=family_revoked, record=record)
