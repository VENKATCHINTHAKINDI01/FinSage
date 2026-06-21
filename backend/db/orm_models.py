"""
SQLAlchemy ORM models.
These define the structure of database tables.
"""

from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Boolean,
    ForeignKey,
    Index,
    Numeric,
    Text,
    Date,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from backend.db.postgres import Base


class User(Base):
    """User account model."""
    __tablename__ = "users"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    financial_profile = relationship(
        "FinancialProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan"
    )
    
    __table_args__ = (
        Index("idx_user_email", "email"),
        Index("idx_user_is_active", "is_active"),
    )


class Session(Base):
    """User session/token model."""
    __tablename__ = "sessions"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    token = Column(String(512), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    ip_address = Column(String(45), nullable=True)  # IPv4 or IPv6
    user_agent = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="sessions")
    
    __table_args__ = (
        Index("idx_session_token", "token"),
        Index("idx_session_expires_at", "expires_at"),
    )


class FinancialProfile(Base):
    """User financial profile model."""
    __tablename__ = "financial_profiles"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, unique=True, index=True)
    
    # Income & Expenses
    annual_income = Column(Numeric(15, 2), nullable=False)  # Up to 99,999,999.99
    monthly_expenses = Column(Numeric(15, 2), nullable=False, default=0)
    investment_amount = Column(Numeric(15, 2), nullable=False, default=0)
    
    # Profile Info
    employment_type = Column(
        String(20),
        nullable=False,
        default="individual",
        index=True
    )  # individual, freelancer, salaried, business, retired
    financial_goal = Column(Text, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="financial_profile")
    
    __table_args__ = (
        Index("idx_financial_profile_user_id", "user_id"),
        Index("idx_financial_profile_employment_type", "employment_type"),
    )


class AuditLog(Base):
    """Audit trail for all database changes."""
    __tablename__ = "audit_logs"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    action = Column(String(100), nullable=False, index=True)  # create, read, update, delete
    entity = Column(String(100), nullable=False, index=True)  # user, session, recommendation
    entity_id = Column(String(36), nullable=True, index=True)
    changes = Column(Text, nullable=True)  # JSON of what changed
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    __table_args__ = (
        Index("idx_audit_log_user_id", "user_id"),
        Index("idx_audit_log_action", "action"),
        Index("idx_audit_log_entity", "entity"),
        Index("idx_audit_log_created_at", "created_at"),
    )


class ComplianceReport(Base):
    """Compliance assessment report for user"""
    __tablename__ = 'compliance_reports'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), ForeignKey('users.id'), nullable=False)
    report_date = Column(DateTime, nullable=False, default=datetime.utcnow)
    compliance_score = Column(Integer, nullable=False)  # 0-100
    audit_readiness = Column(Boolean, nullable=False)
    red_flags = Column(JSON, nullable=True)
    missing_documents = Column(JSON, nullable=True)
    recommendations = Column(JSON, nullable=True)
    risk_level = Column(String(50), nullable=True)  # Low/Medium/High
    saved_status = Column(String(50), nullable=False, default='saved')
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('ix_compliance_reports_user_id', 'user_id'),
        Index('ix_compliance_reports_report_date', 'report_date'),
    )


class AuditHistory(Base):
    """Audit history and findings for user"""
    __tablename__ = 'audit_history'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), ForeignKey('users.id'), nullable=False)
    audit_type = Column(String(50), nullable=False)  # self-audit/external
    audit_date = Column(DateTime, nullable=False, default=datetime.utcnow)
    findings = Column(JSON, nullable=True)
    action_taken = Column(Text, nullable=True)
    resolution_date = Column(Date, nullable=True)
    saved_documents = Column(JSON, nullable=True)
    status = Column(String(50), nullable=False, default='pending')
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('ix_audit_history_user_id', 'user_id'),
        Index('ix_audit_history_audit_date', 'audit_date'),
    )


class ITRFiling(Base):
    """ITR filing details and status"""
    __tablename__ = 'itr_filings'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), ForeignKey('users.id'), nullable=False)
    financial_year = Column(String(20), nullable=False)  # 2024-25
    itr_form = Column(String(20), nullable=False)  # ITR-1/2/4/5
    status = Column(String(50), nullable=False, default='pending')
    filing_date = Column(Date, nullable=True)
    verification_date = Column(Date, nullable=True)
    form_details = Column(JSON, nullable=True)
    checklist = Column(JSON, nullable=True)
    common_mistakes = Column(JSON, nullable=True)
    important_dates = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('ix_itr_filings_user_id', 'user_id'),
        Index('ix_itr_filings_financial_year', 'financial_year'),
        UniqueConstraint('user_id', 'financial_year', 'itr_form', name='uq_itr_filings'),
    )


class TaxCalculation(Base):
    """Complex tax calculation with multiple income sources"""
    __tablename__ = 'tax_calculations'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), ForeignKey('users.id'), nullable=False)
    financial_year = Column(String(20), nullable=False)
    income_sources = Column(JSON, nullable=False)
    deductions = Column(JSON, nullable=True)
    capital_gains = Column(JSON, nullable=True)
    losses = Column(JSON, nullable=True)
    gross_income = Column(Numeric(15, 2), nullable=False)
    taxable_income = Column(Numeric(15, 2), nullable=False)
    income_tax = Column(Numeric(15, 2), nullable=False)
    surcharge = Column(Numeric(15, 2), nullable=False)
    cess = Column(Numeric(15, 2), nullable=False)
    total_tax_liability = Column(Numeric(15, 2), nullable=False)
    effective_rate = Column(Numeric(5, 2), nullable=False)
    optimization_suggestions = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    __table_args__ = (
        Index('ix_tax_calculations_user_id', 'user_id'),
        Index('ix_tax_calculations_financial_year', 'financial_year'),
    )


class FinancialHealthScore(Base):
    """Financial health score with 5 factors"""
    __tablename__ = 'financial_health_scores'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), ForeignKey('users.id'), nullable=False)
    score_date = Column(DateTime, nullable=False, default=datetime.utcnow)
    overall_score = Column(Integer, nullable=False)  # 0-100
    tax_efficiency_score = Column(Integer, nullable=False)  # 20%
    deduction_optimization_score = Column(Integer, nullable=False)  # 20%
    savings_potential_score = Column(Integer, nullable=False)  # 20%
    compliance_status_score = Column(Integer, nullable=False)  # 20%
    investment_diversity_score = Column(Integer, nullable=False)  # 20%
    breakdown = Column(JSON, nullable=True)
    recommendations = Column(JSON, nullable=True)
    trend_vs_last_month = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    __table_args__ = (
        Index('ix_financial_health_scores_user_id', 'user_id'),
        Index('ix_financial_health_scores_score_date', 'score_date'),
    )


class Notification(Base):
    """Sent/pending notifications to user"""
    __tablename__ = 'notifications'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), ForeignKey('users.id'), nullable=False)
    notification_type = Column(String(100), nullable=False)
    channel = Column(String(50), nullable=False)  # email, telegram, sms
    recipient = Column(String(255), nullable=False)
    subject = Column(String(255), nullable=True)
    message = Column(Text, nullable=False)
    data = Column(JSON, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    status = Column(String(50), nullable=False, default='pending')
    retry_count = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('ix_notifications_user_id', 'user_id'),
        Index('ix_notifications_channel', 'channel'),
        Index('ix_notifications_status', 'status'),
        Index('ix_notifications_created_at', 'created_at'),
    )


class NotificationPreference(Base):
    """User notification preferences"""
    __tablename__ = 'notification_preferences'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), ForeignKey('users.id'), nullable=False)
    channel = Column(String(50), nullable=False)  # email, telegram, sms
    enabled = Column(Boolean, nullable=False, default=True)
    frequency = Column(String(50), nullable=False)  # daily, weekly, monthly, as_needed
    preferred_time = Column(Time, nullable=True)
    notification_types = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('ix_notification_preferences_user_id', 'user_id'),
        UniqueConstraint('user_id', 'channel', name='uq_notification_preferences'),
    )


class ScheduledTask(Base):
    """Scheduled automation tasks"""
    __tablename__ = 'scheduled_tasks'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_name = Column(String(255), nullable=False)
    task_type = Column(String(100), nullable=False)
    schedule = Column(String(255), nullable=False)  # Cron expression
    is_active = Column(Boolean, nullable=False, default=True)
    last_run = Column(DateTime, nullable=True)
    next_run = Column(DateTime, nullable=True)
    execution_log = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('ix_scheduled_tasks_is_active', 'is_active'),
        Index('ix_scheduled_tasks_next_run', 'next_run'),
    )


class Report(Base):
    """Generated reports (PDF, etc)"""
    __tablename__ = 'reports'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), ForeignKey('users.id'), nullable=False)
    report_type = Column(String(100), nullable=False)
    format = Column(String(50), nullable=False, default='pdf')
    title = Column(String(255), nullable=False)
    generated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=True)
    file_url = Column(String(500), nullable=True)
    delivery_status = Column(String(50), nullable=False, default='generated')
    email_sent_at = Column(DateTime, nullable=True)
    download_count = Column(Integer, nullable=False, default=0)
    last_downloaded_at = Column(DateTime, nullable=True)
    report_metadata = Column('metadata', JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    __table_args__ = (
        Index('ix_reports_user_id', 'user_id'),
        Index('ix_reports_report_type', 'report_type'),
        Index('ix_reports_generated_at', 'generated_at'),
    )


class RedFlagLog(Base):
    """Track red flags over time"""
    __tablename__ = 'red_flag_logs'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), ForeignKey('users.id'), nullable=False)
    flag_name = Column(String(255), nullable=False)
    severity = Column(String(50), nullable=False)  # Low, Medium, High
    description = Column(Text, nullable=False)
    action_required = Column(Text, nullable=True)
    resolved = Column(Boolean, nullable=False, default=False)
    resolved_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    __table_args__ = (
        Index('ix_red_flag_logs_user_id', 'user_id'),
        Index('ix_red_flag_logs_severity', 'severity'),
        Index('ix_red_flag_logs_resolved', 'resolved'),
    )