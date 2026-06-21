"""
Alembic Migration: Step 9 & 10 Database Tables
===============================================

Creates all new tables for Compliance, Reports, Automation
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from datetime import datetime

# Migration ID and description
revision = 'step_9_10_tables_001'
down_revision = '62965466c4ca'
branch_labels = None
depends_on = None


def upgrade():
    """Create all new tables for Steps 9 & 10"""
    
    # Table 1: compliance_reports
    op.create_table(
        'compliance_reports',
        sa.Column('id', sa.UUID(), nullable=False, primary_key=True, default=sa.func.gen_random_uuid()),
        sa.Column('user_id', sa.String(255), nullable=False),
        sa.Column('report_date', sa.DateTime(), nullable=False, default=datetime.utcnow),
        sa.Column('compliance_score', sa.Integer(), nullable=False),  # 0-100
        sa.Column('audit_readiness', sa.Boolean(), nullable=False),
        sa.Column('red_flags', postgresql.JSON, nullable=True),  # List of red flags
        sa.Column('missing_documents', postgresql.JSON, nullable=True),  # List of missing docs
        sa.Column('recommendations', postgresql.JSON, nullable=True),  # List of recommendations
        sa.Column('risk_level', sa.String(50), nullable=True),  # Low/Medium/High
        sa.Column('saved_status', sa.String(50), nullable=False, default='saved'),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=datetime.utcnow),
        sa.Column('updated_at', sa.DateTime(), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.Index('ix_compliance_reports_user_id', 'user_id'),
        sa.Index('ix_compliance_reports_report_date', 'report_date')
    )
    
    # Table 2: audit_history
    op.create_table(
        'audit_history',
        sa.Column('id', sa.UUID(), nullable=False, primary_key=True, default=sa.func.gen_random_uuid()),
        sa.Column('user_id', sa.String(255), nullable=False),
        sa.Column('audit_type', sa.String(50), nullable=False),  # self-audit/external
        sa.Column('audit_date', sa.DateTime(), nullable=False, default=datetime.utcnow),
        sa.Column('findings', postgresql.JSON, nullable=True),  # Audit findings
        sa.Column('action_taken', sa.Text(), nullable=True),
        sa.Column('resolution_date', sa.Date(), nullable=True),
        sa.Column('saved_documents', postgresql.JSON, nullable=True),  # List of docs
        sa.Column('status', sa.String(50), nullable=False, default='pending'),  # pending/resolved
        sa.Column('created_at', sa.DateTime(), nullable=False, default=datetime.utcnow),
        sa.Column('updated_at', sa.DateTime(), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.Index('ix_audit_history_user_id', 'user_id'),
        sa.Index('ix_audit_history_audit_date', 'audit_date')
    )
    
    # Table 3: itr_filings
    op.create_table(
        'itr_filings',
        sa.Column('id', sa.UUID(), nullable=False, primary_key=True, default=sa.func.gen_random_uuid()),
        sa.Column('user_id', sa.String(255), nullable=False),
        sa.Column('financial_year', sa.String(20), nullable=False),  # 2024-25
        sa.Column('itr_form', sa.String(20), nullable=False),  # ITR-1/2/4/5
        sa.Column('status', sa.String(50), nullable=False, default='pending'),  # pending/filed/verified
        sa.Column('filing_date', sa.Date(), nullable=True),
        sa.Column('verification_date', sa.Date(), nullable=True),
        sa.Column('form_details', postgresql.JSON, nullable=True),
        sa.Column('checklist', postgresql.JSON, nullable=True),  # Filing checklist
        sa.Column('common_mistakes', postgresql.JSON, nullable=True),
        sa.Column('important_dates', postgresql.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=datetime.utcnow),
        sa.Column('updated_at', sa.DateTime(), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.Index('ix_itr_filings_user_id', 'user_id'),
        sa.Index('ix_itr_filings_financial_year', 'financial_year'),
        sa.UniqueConstraint('user_id', 'financial_year', 'itr_form', name='uq_itr_filings')
    )
    
    # Table 4: tax_calculations
    op.create_table(
        'tax_calculations',
        sa.Column('id', sa.UUID(), nullable=False, primary_key=True, default=sa.func.gen_random_uuid()),
        sa.Column('user_id', sa.String(255), nullable=False),
        sa.Column('financial_year', sa.String(20), nullable=False),
        sa.Column('income_sources', postgresql.JSON, nullable=False),  # salary, business, rental, etc
        sa.Column('deductions', postgresql.JSON, nullable=True),
        sa.Column('capital_gains', postgresql.JSON, nullable=True),  # STCG, LTCG
        sa.Column('losses', postgresql.JSON, nullable=True),
        sa.Column('gross_income', sa.Numeric(15, 2), nullable=False),
        sa.Column('taxable_income', sa.Numeric(15, 2), nullable=False),
        sa.Column('income_tax', sa.Numeric(15, 2), nullable=False),
        sa.Column('surcharge', sa.Numeric(15, 2), nullable=False),
        sa.Column('cess', sa.Numeric(15, 2), nullable=False),
        sa.Column('total_tax_liability', sa.Numeric(15, 2), nullable=False),
        sa.Column('effective_rate', sa.Numeric(5, 2), nullable=False),  # Percentage
        sa.Column('optimization_suggestions', postgresql.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=datetime.utcnow),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.Index('ix_tax_calculations_user_id', 'user_id'),
        sa.Index('ix_tax_calculations_financial_year', 'financial_year')
    )
    
    # Table 5: financial_health_scores
    op.create_table(
        'financial_health_scores',
        sa.Column('id', sa.UUID(), nullable=False, primary_key=True, default=sa.func.gen_random_uuid()),
        sa.Column('user_id', sa.String(255), nullable=False),
        sa.Column('score_date', sa.DateTime(), nullable=False, default=datetime.utcnow),
        sa.Column('overall_score', sa.Integer(), nullable=False),  # 0-100
        sa.Column('tax_efficiency_score', sa.Integer(), nullable=False),  # 20% weight
        sa.Column('deduction_optimization_score', sa.Integer(), nullable=False),  # 20% weight
        sa.Column('savings_potential_score', sa.Integer(), nullable=False),  # 20% weight
        sa.Column('compliance_status_score', sa.Integer(), nullable=False),  # 20% weight
        sa.Column('investment_diversity_score', sa.Integer(), nullable=False),  # 20% weight
        sa.Column('breakdown', postgresql.JSON, nullable=True),  # Detailed breakdown
        sa.Column('recommendations', postgresql.JSON, nullable=True),
        sa.Column('trend_vs_last_month', sa.Integer(), nullable=True),  # +/- points
        sa.Column('created_at', sa.DateTime(), nullable=False, default=datetime.utcnow),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.Index('ix_financial_health_scores_user_id', 'user_id'),
        sa.Index('ix_financial_health_scores_score_date', 'score_date')
    )
    
    # Table 6: notifications
    op.create_table(
        'notifications',
        sa.Column('id', sa.UUID(), nullable=False, primary_key=True, default=sa.func.gen_random_uuid()),
        sa.Column('user_id', sa.String(255), nullable=False),
        sa.Column('notification_type', sa.String(100), nullable=False),  # deadline, reminder, report, etc
        sa.Column('channel', sa.String(50), nullable=False),  # email, telegram, sms
        sa.Column('recipient', sa.String(255), nullable=False),  # email address or telegram ID
        sa.Column('subject', sa.String(255), nullable=True),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('data', postgresql.JSON, nullable=True),  # Additional data/links
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, default='pending'),  # pending/sent/failed
        sa.Column('retry_count', sa.Integer(), nullable=False, default=0),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=datetime.utcnow),
        sa.Column('updated_at', sa.DateTime(), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.Index('ix_notifications_user_id', 'user_id'),
        sa.Index('ix_notifications_channel', 'channel'),
        sa.Index('ix_notifications_status', 'status'),
        sa.Index('ix_notifications_created_at', 'created_at')
    )
    
    # Table 7: notification_preferences
    op.create_table(
        'notification_preferences',
        sa.Column('id', sa.UUID(), nullable=False, primary_key=True, default=sa.func.gen_random_uuid()),
        sa.Column('user_id', sa.String(255), nullable=False),
        sa.Column('channel', sa.String(50), nullable=False),  # email, telegram, sms
        sa.Column('enabled', sa.Boolean(), nullable=False, default=True),
        sa.Column('frequency', sa.String(50), nullable=False),  # daily, weekly, monthly, as_needed
        sa.Column('preferred_time', sa.Time(), nullable=True),  # Preferred notification time
        sa.Column('notification_types', postgresql.JSON, nullable=True),  # Types to receive
        sa.Column('created_at', sa.DateTime(), nullable=False, default=datetime.utcnow),
        sa.Column('updated_at', sa.DateTime(), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.Index('ix_notification_preferences_user_id', 'user_id'),
        sa.UniqueConstraint('user_id', 'channel', name='uq_notification_preferences')
    )
    
    # Table 8: scheduled_tasks
    op.create_table(
        'scheduled_tasks',
        sa.Column('id', sa.UUID(), nullable=False, primary_key=True, default=sa.func.gen_random_uuid()),
        sa.Column('task_name', sa.String(255), nullable=False),  # Tax deadline reminder, etc
        sa.Column('task_type', sa.String(100), nullable=False),  # reminder, report, notification
        sa.Column('schedule', sa.String(255), nullable=False),  # Cron expression
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('last_run', sa.DateTime(), nullable=True),
        sa.Column('next_run', sa.DateTime(), nullable=True),
        sa.Column('execution_log', postgresql.JSON, nullable=True),  # List of executions
        sa.Column('created_at', sa.DateTime(), nullable=False, default=datetime.utcnow),
        sa.Column('updated_at', sa.DateTime(), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow),
        sa.Index('ix_scheduled_tasks_is_active', 'is_active'),
        sa.Index('ix_scheduled_tasks_next_run', 'next_run')
    )
    
    # Table 9: reports
    op.create_table(
        'reports',
        sa.Column('id', sa.UUID(), nullable=False, primary_key=True, default=sa.func.gen_random_uuid()),
        sa.Column('user_id', sa.String(255), nullable=False),
        sa.Column('report_type', sa.String(100), nullable=False),  # compliance, financial_health, tax_summary
        sa.Column('format', sa.String(50), nullable=False, default='pdf'),  # pdf
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('generated_at', sa.DateTime(), nullable=False, default=datetime.utcnow),
        sa.Column('file_path', sa.String(500), nullable=False),  # Path to generated file
        sa.Column('file_size', sa.Integer(), nullable=True),  # In bytes
        sa.Column('file_url', sa.String(500), nullable=True),  # URL for download
        sa.Column('delivery_status', sa.String(50), nullable=False, default='generated'),  # generated/emailed/downloaded
        sa.Column('email_sent_at', sa.DateTime(), nullable=True),
        sa.Column('download_count', sa.Integer(), nullable=False, default=0),
        sa.Column('last_downloaded_at', sa.DateTime(), nullable=True),
        sa.Column('metadata', postgresql.JSON, nullable=True),  # Additional report metadata
        sa.Column('created_at', sa.DateTime(), nullable=False, default=datetime.utcnow),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.Index('ix_reports_user_id', 'user_id'),
        sa.Index('ix_reports_report_type', 'report_type'),
        sa.Index('ix_reports_generated_at', 'generated_at')
    )
    
    # Table 10: red_flag_logs (For tracking red flags over time)
    op.create_table(
        'red_flag_logs',
        sa.Column('id', sa.UUID(), nullable=False, primary_key=True, default=sa.func.gen_random_uuid()),
        sa.Column('user_id', sa.String(255), nullable=False),
        sa.Column('flag_name', sa.String(255), nullable=False),
        sa.Column('severity', sa.String(50), nullable=False),  # Low, Medium, High
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('action_required', sa.Text(), nullable=True),
        sa.Column('resolved', sa.Boolean(), nullable=False, default=False),
        sa.Column('resolved_date', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=datetime.utcnow),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.Index('ix_red_flag_logs_user_id', 'user_id'),
        sa.Index('ix_red_flag_logs_severity', 'severity'),
        sa.Index('ix_red_flag_logs_resolved', 'resolved')
    )


def downgrade():
    """Drop all tables (rollback)"""
    
    op.drop_table('red_flag_logs')
    op.drop_table('reports')
    op.drop_table('scheduled_tasks')
    op.drop_table('notification_preferences')
    op.drop_table('notifications')
    op.drop_table('financial_health_scores')
    op.drop_table('tax_calculations')
    op.drop_table('itr_filings')
    op.drop_table('audit_history')
    op.drop_table('compliance_reports')
