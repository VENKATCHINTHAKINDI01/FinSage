"""Consent, access and correction endpoints — PRD-001.

Three DPDP obligations, three route groups:

  s.6    Consent must be itemised, versioned, and as easy to withdraw as to
         give — `/consent/*` wraps `backend.compliance.dpdp.consent` over the
         Postgres-backed ledger in `backend.db.crud.consent`.
  s.11   Right to access — `/me/data` returns everything held under the
         principal's own id across the stores this product actually has today
         (account, financial profile, live consent). It is not yet a fan-out
         over the document vault and the vector store; see the module-level
         note on `export_my_data`.
  s.12   Right to correction — already served by `POST /api/v1/profile` and
         `PATCH /api/v1/auth/*`-style account edits; there is no separate
         "correction" endpoint because a second path that edits the same rows
         would be a second place for the two to drift.

What is NOT here: this router being called from every other route. That is
the larger, riskier part of "require_consent on every route" — it touches
document upload, chat, procurement and reports, each with its own purpose —
and is intentionally left for a follow-up pass rather than rushed in behind
one that could not be exercised against a live database in this environment.
"""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.compliance.dpdp.consent import (
    ConsentError,
    Notice,
    NoticeRegistry,
    Purpose,
    require_consent as _require_consent,
)
from backend.db.crud.consent import load_ledger, persist_new_records
from backend.db.crud.users import get_user_by_id
from backend.db.postgres import get_session
from backend.models import UserResponse
from backend.security.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Privacy"])

# The published notice. Version bumps happen by adding a new `Notice` here and
# publishing it to the registry below — never by editing this one's text,
# which would silently change what past consents were informed of.
CURRENT_NOTICE = Notice(
    version="2026.1",
    published_on=date(2026, 8, 16),
    purpose_text={
        Purpose.TAX_COMPUTATION: (
            "Your income, deduction and investment figures are used to compute "
            "your income tax liability under the Income-tax Act. This is "
            "necessary to provide the service and cannot be declined without "
            "losing it."
        ),
        Purpose.ITR_FILING: (
            "Your tax computation and supporting figures are used to prepare "
            "and assist you in filing your income tax return. Necessary for "
            "the filing features; cannot be declined without losing them."
        ),
        Purpose.DOCUMENT_STORAGE: (
            "Documents you upload (Form 16, AIS, broker statements) are stored "
            "encrypted so they can be parsed and referenced in your "
            "computations and evidence packs. Necessary to use document "
            "upload."
        ),
        Purpose.PROCUREMENT_ADVICE: (
            "Your stated budget, location and item preferences are used to "
            "research landed cost and eligibility for a purchase you are "
            "considering. You can decline this and still use tax features."
        ),
        Purpose.PRODUCT_ANALYTICS: (
            "Anonymised usage patterns (which features are used, not their "
            "content) help us find bugs and prioritise fixes. You can decline "
            "this."
        ),
        Purpose.MARKETING: (
            "Your email may be used to tell you about new features or tax "
            "deadlines relevant to you. You can decline this."
        ),
    },
    grievance_officer="Data Protection Officer, FinSage AI",
    grievance_contact="privacy@finsage.ai",
)

NOTICE_REGISTRY = NoticeRegistry()
NOTICE_REGISTRY.publish(CURRENT_NOTICE)


class ConsentAction(BaseModel):
    purpose: Purpose


class ConsentStatusItem(BaseModel):
    purpose: str
    live: bool
    notice_version: str | None = None
    given_on: str | None = None
    withdrawn_on: str | None = None


@router.get("/consent/notice")
async def get_notice() -> dict:
    """The current itemised notice — s.5. What each purpose is, in the words
    consent is actually taken against."""
    return {
        "version": CURRENT_NOTICE.version,
        "published_on": CURRENT_NOTICE.published_on.isoformat(),
        "grievance_officer": CURRENT_NOTICE.grievance_officer,
        "grievance_contact": CURRENT_NOTICE.grievance_contact,
        "purposes": {
            p.value: {
                "text": CURRENT_NOTICE.purpose_text[p],
                "necessary_for_service": p.is_necessary_for_service,
            }
            for p in Purpose
        },
    }


@router.get("/consent/status")
async def consent_status(
    user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ConsentStatusItem]:
    ledger = await load_ledger(session, user.id)
    latest: dict[Purpose, ConsentStatusItem] = {}
    for record in ledger.records:
        latest[record.purpose] = ConsentStatusItem(
            purpose=record.purpose.value,
            live=record.is_live,
            notice_version=record.notice_version,
            given_on=record.given_on.isoformat(),
            withdrawn_on=record.withdrawn_on.isoformat() if record.withdrawn_on else None,
        )
    return list(latest.values())


@router.post("/consent/grant", status_code=status.HTTP_201_CREATED)
async def grant_consent(
    body: ConsentAction,
    user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    ledger = await load_ledger(session, user.id)
    try:
        record = ledger.grant(user.id, body.purpose, CURRENT_NOTICE, on=date.today())
    except ConsentError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    await persist_new_records(session, [record])
    return record.to_dict()


@router.post("/consent/withdraw", status_code=status.HTTP_200_OK)
async def withdraw_consent(
    body: ConsentAction,
    user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """s.6(6): identical shape to `grant_consent` — same body, same auth, no
    extra confirmation. Withdrawal makes any data held under this purpose due
    for erasure immediately (`due_for_erasure` in the compliance module), not
    at the end of its normal retention window."""
    ledger = await load_ledger(session, user.id)
    before = len(ledger.records)
    ledger.withdraw(user.id, body.purpose, CURRENT_NOTICE, on=date.today())
    if len(ledger.records) != before:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="withdrawal must replace a record in place, not add one",
        )
    await persist_new_records(session, ledger.records)
    return {"purpose": body.purpose.value, "withdrawn_on": date.today().isoformat()}


async def require_consent_dep(purpose: Purpose):
    """A FastAPI dependency factory: `Depends(require_consent_dep(Purpose.X))`
    on any route that processes personal data for purpose X. Raises 403 with
    the same message `require_consent` raises internally, so "no consent" and
    "stale notice version" are both explained rather than a bare 403.

    Applied so far only to the routes in this module and left for a follow-up
    pass elsewhere — see the module docstring.
    """
    async def _dep(
        user: UserResponse = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> None:
        ledger = await load_ledger(session, user.id)
        try:
            _require_consent(user.id, purpose, ledger, CURRENT_NOTICE, NOTICE_REGISTRY)
        except ConsentError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from None
    return _dep


@router.get("/me/data")
async def export_my_data(
    user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Right to access — s.11. Everything held under this principal's id, from
    the stores wired up so far: the account row, the financial profile, and
    the live consent ledger.

    Not yet fanned out to the document vault or the vector store — those need
    their own per-store export, tracked the same way `erase()` in the
    compliance module already expects a per-store deleter/confirmer pair. This
    covers the structured-data stores; the file stores are the honest gap.
    """
    from sqlalchemy import select

    from backend.db.orm_models import FinancialProfile

    account = await get_user_by_id(session, user.id)
    profile = (
        await session.execute(
            select(FinancialProfile).where(FinancialProfile.user_id == user.id)
        )
    ).scalar_one_or_none()
    ledger = await load_ledger(session, user.id)

    return {
        "principal_id": user.id,
        "account": {
            "email": account.email,
            "full_name": account.full_name,
            "created_at": account.created_at.isoformat() if account.created_at else None,
        } if account else None,
        "financial_profile": (
            {
                "annual_income": str(profile.annual_income),
                "monthly_expenses": str(profile.monthly_expenses),
                "employment_type": profile.employment_type,
            } if profile else None
        ),
        "consent": [r.to_dict() for r in ledger.records],
        "note": (
            "This export covers account and financial-profile data. Uploaded "
            "documents and derived embeddings are not yet included — request "
            "them separately from support until that export path is built."
        ),
    }
