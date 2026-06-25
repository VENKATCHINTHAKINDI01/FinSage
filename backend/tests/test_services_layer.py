import pytest
import asyncio
from datetime import datetime, date, time
from backend.db.postgres import get_session_maker
from backend.db.orm_models import User
from backend.db.crud.audit_log import create_audit_log, get_audit_logs
from backend.db.crud.recommendations import (
    get_user_compliance_recommendations,
    get_user_tax_suggestions,
    get_user_red_flags
)
from backend.services.health_scorer import FinancialHealthScorer
from backend.services.report_generator import ReportGeneratorService
from backend.services.notification import NotificationService
from backend.services.alert_service import AlertService
from backend.services.document_service import DocumentService
from sqlalchemy import delete

# Define a persistent test user ID to avoid violating foreign key constraints
TEST_USER_ID = "test-user-services-123"

@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="module")
async def db_session():
    session_maker = await get_session_maker()
    async with session_maker() as session:
        # Ensure a test user exists in the users table first to satisfy foreign key constraints
        # users table columns: id, email, full_name, password_hash, is_active, created_at, updated_at
        user = await session.get(User, TEST_USER_ID)
        if not user:
            user = User(
                id=TEST_USER_ID,
                email="test_services@finsage.ai",
                full_name="Services Tester",
                password_hash="fake-hash-12345",
                is_active=True
            )
            session.add(user)
            await session.commit()
            
        yield session
        
        # Cleanup test user data at the end
        try:
            # We don't necessarily delete the user to keep things simple, or we can clean up:
            pass
        except Exception:
            pass

@pytest.mark.asyncio
async def test_crud_audit_log(db_session):
    # Test create_audit_log
    log = await create_audit_log(
        db=db_session,
        user_id=TEST_USER_ID,
        action="test_action",
        entity="test_entity",
        entity_id="123",
        changes="{'field': 'value'}",
        ip_address="127.0.0.1"
    )
    assert log.id is not None
    assert log.action == "test_action"
    
    # Test get_audit_logs
    logs = await get_audit_logs(db=db_session, user_id=TEST_USER_ID, action="test_action")
    assert len(logs) > 0
    assert logs[0].entity == "test_entity"

@pytest.mark.asyncio
async def test_health_scorer_service(db_session):
    scorer = FinancialHealthScorer(db_session)
    
    profile_data = {
        "annual_income": 1500000,
        "deductions": {
            "80C": 120000,
            "80D": 25000
        },
        "investments": {
            "elss": 50000,
            "ppf": 70000
        },
        "tax_liability": 180000
    }
    
    score_record = await scorer.calculate_and_save_score(TEST_USER_ID, profile_data)
    assert score_record.id is not None
    assert 0 <= score_record.overall_score <= 100
    assert "deduction_optimization" in score_record.breakdown

@pytest.mark.asyncio
async def test_report_generator_service(db_session):
    service = ReportGeneratorService(db_session)
    
    analysis_data = {
        "total_savings": 45000,
        "deductions": {"80C": 150000}
    }
    
    report = await service.generate_and_save_report(
        user_id=TEST_USER_ID,
        report_type="tax_summary",
        title="Test Tax Analysis",
        analysis_data=analysis_data,
        report_format="html"
    )
    
    assert report.id is not None
    assert report.format == "html"
    assert report.download_count == 0
    
    # Record download
    updated_report = await service.record_download(report.id)
    assert updated_report.download_count == 1
    assert updated_report.delivery_status == "downloaded"
    
    # Check user reports
    reports = await service.get_user_reports(TEST_USER_ID)
    assert len(reports) > 0

@pytest.mark.asyncio
async def test_notification_service(db_session):
    service = NotificationService(db_session)
    
    # Set preferences
    pref = await service.set_user_preference(
        user_id=TEST_USER_ID,
        channel="email",
        enabled=True,
        frequency="weekly"
    )
    assert pref.channel == "email"
    assert pref.enabled is True
    
    # Send allowed notification
    notif = await service.send_notification(
        user_id=TEST_USER_ID,
        notification_type="reminder",
        channel="email",
        recipient="test@finsage.ai",
        subject="Test Subject",
        message="Hello World"
    )
    assert notif.status == "sent"
    
    # Disable channel
    await service.set_user_preference(
        user_id=TEST_USER_ID,
        channel="sms",
        enabled=False
    )
    
    # Send disabled channel notification
    notif_disabled = await service.send_notification(
        user_id=TEST_USER_ID,
        notification_type="alert",
        channel="sms",
        recipient="1234567890",
        subject=None,
        message="Disabled Test"
    )
    assert notif_disabled.status == "failed"
    assert notif_disabled.error_message == "Channel disabled by user preferences"

@pytest.mark.asyncio
async def test_alert_service(db_session):
    service = AlertService(db_session)
    
    # Log red flag
    flag = await service.log_red_flag(
        user_id=TEST_USER_ID,
        flag_name="Test Red Flag",
        severity="High",
        description="Filing variance too high"
    )
    assert flag.id is not None
    assert flag.resolved is False
    
    # Query flag CRUD helper
    flags = await get_user_red_flags(db_session, TEST_USER_ID, resolved=False)
    assert len(flags) > 0
    assert flags[0].flag_name == "Test Red Flag"
    
    # Resolve flag
    resolved_flag = await service.resolve_red_flag(flag.id)
    assert resolved_flag.resolved is True
    assert resolved_flag.resolved_date is not None
    
    # Create scheduled task
    task = await service.create_scheduled_task(
        task_name="Verify Deadline Tasks",
        task_type="reminder",
        schedule="0 0 * * *"
    )
    assert task.id is not None
    assert task.is_active is True
    
    # Execute scheduled task
    updated_task = await service.execute_scheduled_task(task.id, status="success", log_message="Execution ran fine")
    assert updated_task.last_run is not None
    assert len(updated_task.execution_log) == 1

@pytest.mark.asyncio
async def test_document_service(db_session):
    service = DocumentService(db_session)
    
    # Log audit
    audit = await service.log_audit_history(
        user_id=TEST_USER_ID,
        audit_type="self-audit",
        findings={"variance": "none"},
        saved_documents=["pan_card.pdf"]
    )
    assert audit.id is not None
    assert audit.status == "pending"
    
    # Resolve audit
    resolved = await service.resolve_audit_history(
        audit_id=audit.id,
        action_taken="Linked Aadhaar and fixed name mismatch",
        resolution_date=date.today()
    )
    assert resolved.status == "resolved"
    assert resolved.action_taken == "Linked Aadhaar and fixed name mismatch"
    
    # Query history list
    history = await service.get_user_audit_history(TEST_USER_ID)
    assert len(history) > 0


@pytest.mark.asyncio
async def test_calculate_health_score_new_api(db_session):
    # Test set_db method
    scorer = FinancialHealthScorer()
    assert scorer.db is None
    scorer.set_db(db_session)
    assert scorer.db == db_session
    
    financial_data = {
        "effective_tax_rate": 15,
        "tds_mismatch": False,
        "optimization_done": True,
        "total_deductions": 750000,
        "deduction_count": 4,
        "compliance_score": 85,
        "red_flags": 1,
        "audit_ready": True,
        "missing_documents": 1,
        "life_insurance": True,
        "mutual_funds": True,
        "ppf": True,
        "investment_options_available": 5
    }
    
    result_dict = await scorer.calculate_health_score(TEST_USER_ID, financial_data)
    assert result_dict["success"] is True
    result = result_dict["result"]
    assert 0 <= result["overall_score"] <= 100
    assert "health_status" in result
    assert "breakdown" in result
    assert "trend" in result
    assert "recommendations" in result
    assert "score_date" in result
    assert "action_items" in result
    assert "db_record" in result_dict
    
    db_record = result_dict["db_record"]
    assert db_record.id is not None
    assert db_record.overall_score == result["overall_score"]

