"""sessions.expires_at/created_at -> timezone-aware — PRD-002 bugfix

Found by actually running the app against a live database for the first
time: `POST /api/v1/auth/register` 500'd on every attempt. Every caller
builds `expires_at` from `datetime.now(timezone.utc)` (aware); the column was
a naive `TIMESTAMP`, and asyncpg refuses to encode an aware value into it.
The unit/golden suites never caught this because they exercise pure logic,
not an actual INSERT against Postgres.

Revision ID: prd_002_sessions_tz_aware
Revises: prd_001_consent_records
Create Date: 2026-08-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "prd_002_sessions_tz_aware"
down_revision: Union[str, None] = "prd_001_consent_records"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing naive timestamps are interpreted as UTC (every row so far was
    # written from datetime.now(timezone.utc) with the tzinfo silently
    # dropped by the naive column) — `USING expires_at AT TIME ZONE 'UTC'`
    # says so explicitly rather than trusting the session's local timezone.
    op.execute(
        "ALTER TABLE sessions ALTER COLUMN expires_at TYPE TIMESTAMP WITH TIME ZONE "
        "USING expires_at AT TIME ZONE 'UTC'"
    )
    op.execute(
        "ALTER TABLE sessions ALTER COLUMN created_at TYPE TIMESTAMP WITH TIME ZONE "
        "USING created_at AT TIME ZONE 'UTC'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE sessions ALTER COLUMN expires_at TYPE TIMESTAMP")
    op.execute("ALTER TABLE sessions ALTER COLUMN created_at TYPE TIMESTAMP")
