"""Refresh session table for rotation and revocation — PRD-002

Backs backend.security.sessions.SessionStore. Refresh tokens are single use;
this table is how a second presentation of an already-rotated token is
detected, and how a revoked login family is checked on every request.

Revision ID: prd_002_refresh_sessions
Revises: step_9_10_tables_001
Create Date: 2026-08-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "prd_002_refresh_sessions"
down_revision: Union[str, None] = "step_9_10_tables_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "refresh_sessions",
        sa.Column("jti", sa.String(64), primary_key=True),
        sa.Column("family", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="active"),
        sa.Column("replaced_by", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("idx_refresh_session_family_state", "refresh_sessions", ["family", "state"])
    op.create_index("idx_refresh_session_user_id", "refresh_sessions", ["user_id"])
    op.create_index("idx_refresh_session_expires_at", "refresh_sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_table("refresh_sessions")
