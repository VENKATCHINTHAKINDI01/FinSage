"""Consent ledger table — PRD-001

Backs backend.compliance.dpdp.consent.ConsentLedger. Append-only: a
withdrawal is a new row, not a mutation, so the evidence that consent was
ever held survives its own withdrawal.

Revision ID: prd_001_consent_records
Revises: prd_002_refresh_sessions
Create Date: 2026-08-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "prd_001_consent_records"
down_revision: Union[str, None] = "prd_002_refresh_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "consent_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("principal_id", sa.String(36), nullable=False),
        sa.Column("purpose", sa.String(64), nullable=False),
        sa.Column("notice_version", sa.String(32), nullable=False),
        sa.Column("given_on", sa.Date(), nullable=False),
        sa.Column("withdrawn_on", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["principal_id"], ["users.id"]),
    )
    op.create_index("idx_consent_principal_purpose", "consent_records", ["principal_id", "purpose"])


def downgrade() -> None:
    op.drop_table("consent_records")
