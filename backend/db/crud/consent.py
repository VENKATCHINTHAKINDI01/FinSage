"""Postgres-backed adapter for `backend.compliance.dpdp.consent` — PRD-001.

Same shape as `backend.db.crud.refresh_sessions`: the consent logic in
`ConsentLedger.grant`/`.withdraw` and `require_consent` is pure, tested
against an in-memory ledger. This loads one principal's records into that
in-memory shape, lets the pure functions decide, and writes back only what
changed.

Unlike sessions, consent is append-only and small per user (one row per
purpose per grant/withdraw event, not per request), so loading a principal's
full history is cheap and never partial — a compliance record with a gap in
it is worse than the record it is trying to replace.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.compliance.dpdp.consent import ConsentLedger, ConsentRecord, Purpose
from backend.db.orm_models import ConsentRecord as ConsentRow


def _to_record(row: ConsentRow) -> ConsentRecord:
    return ConsentRecord(
        principal_id=row.principal_id,
        purpose=Purpose(row.purpose),
        notice_version=row.notice_version,
        given_on=row.given_on,
        withdrawn_on=row.withdrawn_on,
    )


async def load_ledger(db: AsyncSession, principal_id: str) -> ConsentLedger:
    """Every consent event this principal has ever generated."""
    result = await db.execute(
        select(ConsentRow)
        .where(ConsentRow.principal_id == principal_id)
        .order_by(ConsentRow.given_on)
    )
    ledger = ConsentLedger()
    ledger.records = [_to_record(row) for row in result.scalars()]
    return ledger


async def persist_new_records(db: AsyncSession, records: list[ConsentRecord]) -> None:
    """`ConsentLedger.grant`/`.withdraw` mutate the ledger's list in place —
    append for a grant, replace-in-place for a withdrawal (a new frozen record
    at the same list index). This mirrors that: any row identified by
    `(principal_id, purpose, given_on)` is upserted, which naturally becomes
    an UPDATE for the withdrawal case and an INSERT for a fresh grant.
    """
    for record in records:
        result = await db.execute(
            select(ConsentRow).where(
                ConsentRow.principal_id == record.principal_id,
                ConsentRow.purpose == record.purpose.value,
                ConsentRow.given_on == record.given_on,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = ConsentRow(
                principal_id=record.principal_id,
                purpose=record.purpose.value,
                given_on=record.given_on,
            )
            db.add(row)
        row.notice_version = record.notice_version
        row.withdrawn_on = record.withdrawn_on
    await db.commit()


async def is_consent_live(db: AsyncSession, principal_id: str, purpose: Purpose) -> bool:
    """The read the middleware/route dependency actually needs — no ledger
    reconstruction, just whether the most recent record for this purpose is
    live. Notice-version staleness is a separate, explicit check
    (`require_consent` against the live `Notice`), not folded in here."""
    result = await db.execute(
        select(ConsentRow)
        .where(ConsentRow.principal_id == principal_id, ConsentRow.purpose == purpose.value)
        .order_by(ConsentRow.given_on.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return row is not None and row.withdrawn_on is None


__all__ = ["is_consent_live", "load_ledger", "persist_new_records"]
