"""All remaining naive DateTime columns -> timezone-aware — PRD-007 bugfix

Found the same way the sessions.expires_at bug was found: a real load test
against a live database, not a unit test. `alert_service.resolve_red_flag`
500'd trying to write an aware `datetime.now(timezone.utc)` into
`red_flag_logs.resolved_date`, a naive column — the identical failure mode
as the PRD-002 sessions bug, just in a table nothing had exercised with a
real write yet. A grep across orm_models.py found the same pattern on every
table added in the Step 9 & 10 migration: 28 naive DateTime columns across
10 tables, all paired with code that builds aware datetimes.

Existing naive rows are interpreted as UTC on conversion (every writer used
UTC even though the column dropped the tzinfo), same policy as the sessions
migration.

Revision ID: prd_007_tz_aware_datetimes
Revises: prd_002_sessions_tz_aware
Create Date: 2026-08-17
"""

from typing import Sequence, Union

from alembic import op

revision: str = "prd_007_tz_aware_datetimes"
down_revision: Union[str, None] = "prd_002_sessions_tz_aware"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, [naive datetime columns])
TABLES = [
    ("financial_profiles", ["created_at", "updated_at"]),
    ("audit_logs", ["created_at"]),
    ("compliance_reports", ["report_date", "created_at", "updated_at"]),
    ("audit_history", ["audit_date", "created_at", "updated_at"]),
    ("itr_filings", ["created_at", "updated_at"]),
    ("tax_calculations", ["created_at"]),
    ("financial_health_scores", ["score_date", "created_at"]),
    ("notifications", ["sent_at", "created_at", "updated_at"]),
    ("notification_preferences", ["created_at", "updated_at"]),
    ("scheduled_tasks", ["last_run", "next_run", "created_at", "updated_at"]),
    ("reports", ["generated_at", "email_sent_at", "last_downloaded_at", "created_at"]),
    ("red_flag_logs", ["resolved_date", "created_at"]),
]


def upgrade() -> None:
    for table, columns in TABLES:
        for column in columns:
            op.execute(
                f"ALTER TABLE {table} ALTER COLUMN {column} TYPE TIMESTAMP WITH TIME ZONE "
                f"USING {column} AT TIME ZONE 'UTC'"
            )


def downgrade() -> None:
    for table, columns in TABLES:
        for column in columns:
            op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE TIMESTAMP")
