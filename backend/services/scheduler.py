"""
Service to schedule automated background tasks using APScheduler.
"""

import logging
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.db.orm_models import ScheduledTask

logger = logging.getLogger(__name__)


class SchedulerService:
    """
    Schedule automated tasks.
    
    Jobs:
    1. Tax Deadline Reminder (July 20)
    2. Annual Review Reminder (April 1)
    3. Investment Deadline Reminder (Mar 25, Jun 25, Sep 25, Dec 25)
    4. Weekly Tax Tips (Monday 10 AM)
    5. Monthly Health Report (1st of month, 9 AM)
    
    Features:
    • Persistent scheduling
    • Execution logging
    • Failure handling
    • Database tracking
    """
    
    def __init__(self, db: Optional[Session] = None):
        self.name = "scheduler_service"
        self.db = db
        self.logger = logging.getLogger(f"service.{self.name}")
        self.scheduler = BackgroundScheduler()
        self.loop = None
    
    def set_db(self, db: Session):
        """Set database session."""
        self.db = db
        return self
    
    def initialize_scheduler(self):
        """Initialize and start scheduler with all jobs."""
        try:
            self.logger.info("Initializing scheduler...")
            
            # Capture the current running event loop if any
            try:
                self.loop = asyncio.get_running_loop()
            except RuntimeError:
                self.loop = None
            
            # Define all scheduled jobs
            jobs = [
                {
                    "id": "tax_deadline_reminder",
                    "func": self._tax_deadline_reminder,
                    "trigger": CronTrigger(month=7, day=20, hour=9),  # July 20, 9 AM
                    "name": "Tax Deadline Reminder (July 31)"
                },
                {
                    "id": "annual_review_reminder",
                    "func": self._annual_review_reminder,
                    "trigger": CronTrigger(month=4, day=1, hour=9),  # April 1, 9 AM
                    "name": "Annual Review Reminder"
                },
                {
                    "id": "investment_deadline_reminder",
                    "func": self._investment_deadline_reminder,
                    "trigger": CronTrigger(month="3,6,9,12", day=25, hour=9),  # 25th of Q-end months
                    "name": "Investment Deadline Reminder"
                },
                {
                    "id": "weekly_tax_tips",
                    "func": self._weekly_tax_tips,
                    "trigger": CronTrigger(day_of_week=0, hour=10),  # Monday 10 AM
                    "name": "Weekly Tax Tips"
                },
                {
                    "id": "monthly_health_report",
                    "func": self._monthly_health_report,
                    "trigger": CronTrigger(day=1, hour=9),  # 1st of month, 9 AM
                    "name": "Monthly Financial Health Report"
                }
            ]
            
            # Add jobs to scheduler
            for job in jobs:
                self.scheduler.add_job(
                    func=job["func"],
                    trigger=job["trigger"],
                    id=job["id"],
                    name=job["name"],
                    misfire_grace_time=600,  # 10 min grace period
                    replace_existing=True
                )
                self.logger.info(f"✓ Scheduled: {job['name']}")
            
            # Start scheduler
            if not self.scheduler.running:
                self.scheduler.start()
                self.logger.info("✅ Scheduler started successfully")
            
            return {
                "success": True,
                "jobs_scheduled": len(jobs),
                "scheduler_running": self.scheduler.running
            }
        
        except Exception as e:
            self.logger.error(f"Error initializing scheduler: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def shutdown_scheduler(self):
        """Shutdown scheduler."""
        try:
            if self.scheduler.running:
                self.scheduler.shutdown()
                self.logger.info("Scheduler shutdown")
            return {"success": True}
        except Exception as e:
            self.logger.error(f"Error shutting down scheduler: {e}")
            return {"success": False, "error": str(e)}

    def _run_async(self, coro):
        """Run a coroutine safely from sync scheduler thread or same loop thread."""
        try:
            try:
                current_loop = asyncio.get_running_loop()
            except RuntimeError:
                current_loop = None
                
            if current_loop and self.loop and current_loop == self.loop:
                # We are in the same thread as the running event loop.
                # Scheduling task without blocking to prevent deadlock.
                asyncio.create_task(coro)
                return None
            elif self.loop and self.loop.is_running():
                future = asyncio.run_coroutine_threadsafe(coro, self.loop)
                return future.result(timeout=60)
            else:
                return asyncio.run(coro)
        except Exception as e:
            self.logger.error(f"Error running coroutine: {e}", exc_info=True)
            raise e
    
    # ===== JOB FUNCTIONS =====
    
    def _tax_deadline_reminder(self):
        """Job 1: Tax deadline reminder (July 20)."""
        self._run_async(self._async_tax_deadline_reminder())

    async def _async_tax_deadline_reminder(self):
        try:
            self.logger.info("Running: Tax Deadline Reminder")
            
            from backend.services.notification import NotificationService, send_tax_deadline_reminder
            from backend.db.postgres import get_session_maker
            from backend.db.orm_models import User
            
            session_maker = await get_session_maker()
            async with session_maker() as db:
                res = await db.execute(select(User))
                users = res.scalars().all()
                
                notification_service = NotificationService(db)
                for user in users:
                    days_remaining = 11  # July 31 - July 20
                    if user.email:
                        await send_tax_deadline_reminder(
                            notification_service,
                            user.email,
                            user.id,
                            days_remaining
                        )
            
            await self._log_execution("tax_deadline_reminder", "success")
            self.logger.info("✓ Tax Deadline Reminder sent to all users")
        except Exception as e:
            self.logger.error(f"Error in tax deadline reminder: {e}", exc_info=True)
            await self._log_execution("tax_deadline_reminder", "failed", str(e))
    
    def _annual_review_reminder(self):
        """Job 2: Annual review reminder (April 1)."""
        self._run_async(self._async_annual_review_reminder())

    async def _async_annual_review_reminder(self):
        try:
            self.logger.info("Running: Annual Review Reminder")
            
            from backend.services.notification import NotificationService
            from backend.db.postgres import get_session_maker
            from backend.db.orm_models import User
            
            session_maker = await get_session_maker()
            async with session_maker() as db:
                res = await db.execute(select(User))
                users = res.scalars().all()
                
                notification_service = NotificationService(db)
                for user in users:
                    if user.email:
                        await notification_service.send_email(
                            recipient_email=user.email,
                            subject="📅 Your FinSage Annual Financial Review",
                            message="Dear User,\n\nIt is time for your annual review. Log in to start optimization.",
                            user_id=user.id
                        )
            
            await self._log_execution("annual_review_reminder", "success")
            self.logger.info("✓ Annual Review Reminder sent")
        except Exception as e:
            self.logger.error(f"Error in annual review reminder: {e}", exc_info=True)
            await self._log_execution("annual_review_reminder", "failed", str(e))
    
    def _investment_deadline_reminder(self):
        """Job 3: Investment deadline reminder (25th of Q-end months)."""
        self._run_async(self._async_investment_deadline_reminder())

    async def _async_investment_deadline_reminder(self):
        try:
            self.logger.info("Running: Investment Deadline Reminder")
            
            now = datetime.now()
            quarter_ends = {
                3: "March 31 (FY End)",
                6: "June 30 (Q4)",
                9: "September 30 (Q3)",
                12: "December 31 (Q2)"
            }
            quarter_name = quarter_ends.get(now.month, "Unknown Quarter")
            
            from backend.services.notification import NotificationService
            from backend.db.postgres import get_session_maker
            from backend.db.orm_models import User
            
            session_maker = await get_session_maker()
            async with session_maker() as db:
                res = await db.execute(select(User))
                users = res.scalars().all()
                
                notification_service = NotificationService(db)
                for user in users:
                    if user.email:
                        await notification_service.send_email(
                            recipient_email=user.email,
                            subject="⏳ Investment Deadline Approaching",
                            message=f"Dear User,\n\nThis is a reminder for the upcoming {quarter_name} investment deadline.",
                            user_id=user.id
                        )
            
            await self._log_execution("investment_deadline_reminder", "success")
            self.logger.info("✓ Investment Deadline Reminder sent")
        except Exception as e:
            self.logger.error(f"Error in investment deadline reminder: {e}", exc_info=True)
            await self._log_execution("investment_deadline_reminder", "failed", str(e))
    
    def _weekly_tax_tips(self):
        """Job 4: Weekly tax tips (Every Monday 10 AM)."""
        self._run_async(self._async_weekly_tax_tips())

    async def _async_weekly_tax_tips(self):
        try:
            self.logger.info("Running: Weekly Tax Tips")
            
            tips = [
                "Maximize your 80C deductions before March 31. Options: ELSS, PPF, NSC, Life Insurance",
                "Health insurance premiums (80D) can save ₹30,000+ in taxes. Minimum ₹150,000 limit",
                "Education loan interest (80E) is deductible without limit. Check your Form 16",
                "NPS contributions (80CCD) offer additional ₹50,000 deduction beyond 80C",
                "Long-term capital gains on mutual funds taxed at only 20%. LTCG is investor-friendly",
                "Rental income can be claimed with 30% standard deduction. Maintain proper records",
                "TDS mismatch? Verify your 26AS statement on incometax.gov.in",
                "Don't miss advance tax deadlines. Calculate for Apr, Jun, Sep, Dec",
                "Claim medical expenses (80DDB) for serious illnesses. Up to ₹100,000 limit",
                "Charitable donations (80G) get 50-100% deduction. Plan your giving wisely"
            ]
            
            now = datetime.now()
            week_number = now.isocalendar()[1]
            tip = tips[week_number % len(tips)]
            
            from backend.services.notification import NotificationService, send_weekly_tax_tip
            from backend.db.postgres import get_session_maker
            from backend.db.orm_models import User
            
            session_maker = await get_session_maker()
            async with session_maker() as db:
                res = await db.execute(select(User))
                users = res.scalars().all()
                
                notification_service = NotificationService(db)
                for user in users:
                    if user.email:
                        await send_weekly_tax_tip(
                            notification_service,
                            user.email,
                            user.id,
                            tip
                        )
            
            await self._log_execution("weekly_tax_tips", "success")
            self.logger.info("✓ Weekly Tax Tips sent")
        except Exception as e:
            self.logger.error(f"Error in weekly tax tips: {e}", exc_info=True)
            await self._log_execution("weekly_tax_tips", "failed", str(e))
    
    def _monthly_health_report(self):
        """Job 5: Monthly financial health report (1st of month)."""
        self._run_async(self._async_monthly_health_report())

    async def _async_monthly_health_report(self):
        try:
            self.logger.info("Running: Monthly Health Report")
            
            from backend.services.notification import NotificationService, send_financial_health_report
            from backend.db.postgres import get_session_maker
            from backend.db.orm_models import User
            
            session_maker = await get_session_maker()
            async with session_maker() as db:
                res = await db.execute(select(User))
                users = res.scalars().all()
                
                notification_service = NotificationService(db)
                for user in users:
                    if user.email:
                        await send_financial_health_report(
                            notification_service,
                            user.email,
                            user.id,
                            75  # Default health score value for monthly report
                        )
            
            await self._log_execution("monthly_health_report", "success")
            self.logger.info("✓ Monthly Health Reports generated and sent")
        except Exception as e:
            self.logger.error(f"Error in monthly health report: {e}", exc_info=True)
            await self._log_execution("monthly_health_report", "failed", str(e))
    
    # ===== HELPER FUNCTIONS =====
    
    async def _log_execution(
        self,
        task_name: str,
        status: str,
        error_message: str = None
    ):
        """Log task execution to database."""
        try:
            if not self.db:
                # Open database session locally
                from backend.db.postgres import get_session_maker
                session_maker = await get_session_maker()
                async with session_maker() as db:
                    await self._log_execution_with_db(db, task_name, status, error_message)
            else:
                await self._log_execution_with_db(self.db, task_name, status, error_message)
        except Exception as e:
            self.logger.error(f"Error logging execution: {e}", exc_info=True)

    async def _log_execution_with_db(
        self,
        db_session,
        task_name: str,
        status: str,
        error_message: str = None
    ):
        if hasattr(db_session, "execute"):
            query = select(ScheduledTask).where(ScheduledTask.task_name == task_name)
            res = await db_session.execute(query)
            task = res.scalars().first()
        else:
            task = db_session.query(ScheduledTask).filter(
                ScheduledTask.task_name == task_name
            ).first()
            
        if not task:
            task = ScheduledTask(
                task_name=task_name,
                task_type="notification",
                schedule="See cron in code",
                is_active=True,
                execution_log=[]
            )
            db_session.add(task)
            if hasattr(db_session, "flush"):
                flush_res = db_session.flush()
                if asyncio.iscoroutine(flush_res):
                    await flush_res
                    
        # Update execution info
        task.last_run = datetime.utcnow()
        task.next_run = self._get_next_run_time(task_name)
        
        # Add to execution log
        current_logs = list(task.execution_log) if task.execution_log else []
        execution_record = {
            "timestamp": datetime.utcnow().isoformat(),
            "status": status,
            "error": error_message
        }
        current_logs.append(execution_record)
        task.execution_log = current_logs
        
        if hasattr(db_session, "commit"):
            commit_res = db_session.commit()
            if asyncio.iscoroutine(commit_res):
                await commit_res
        self.logger.info(f"Logged execution: {task_name} - {status}")
    
    def _get_next_run_time(self, task_name: str) -> datetime:
        """Get next run time for a task."""
        now = datetime.now()
        if task_name == "tax_deadline_reminder":
            return datetime(now.year if now.month < 7 or (now.month == 7 and now.day <= 20) else now.year + 1, 7, 20, 9, 0, 0)
        elif task_name == "annual_review_reminder":
            return datetime(now.year if now.month < 4 or (now.month == 4 and now.day <= 1) else now.year + 1, 4, 1, 9, 0, 0)
        elif task_name == "weekly_tax_tips":
            days_ahead = 0 - now.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            next_run = now + timedelta(days=days_ahead)
            return datetime(next_run.year, next_run.month, next_run.day, 10, 0, 0)
        elif task_name == "monthly_health_report":
            if now.day == 1 and now.hour < 9:
                return datetime(now.year, now.month, 1, 9, 0, 0)
            else:
                next_month = now.month + 1 if now.month < 12 else 1
                year = now.year if now.month < 12 else now.year + 1
                return datetime(year, next_month, 1, 9, 0, 0)
        elif task_name == "investment_deadline_reminder":
            q_months = [3, 6, 9, 12]
            for m in q_months:
                if now.month < m or (now.month == m and now.day <= 25):
                    return datetime(now.year, m, 25, 9, 0, 0)
            return datetime(now.year + 1, 3, 25, 9, 0, 0)
        return now + timedelta(days=1)
    
    def get_job_status(self) -> Dict[str, Any]:
        """Get status of all scheduled jobs."""
        try:
            if not self.scheduler.running:
                return {"scheduler_running": False}
            
            jobs_info = []
            for job in self.scheduler.get_jobs():
                jobs_info.append({
                    "id": job.id,
                    "name": job.name,
                    "next_run_time": str(job.next_run_time) if job.next_run_time else None,
                    "trigger": str(job.trigger)
                })
            
            return {
                "scheduler_running": True,
                "total_jobs": len(jobs_info),
                "jobs": jobs_info
            }
        except Exception as e:
            self.logger.error(f"Error getting job status: {e}")
            return {"error": str(e)}


# Global scheduler instance
scheduler_service = None


def init_scheduler(db: Optional[Session] = None) -> Dict[str, Any]:
    """Initialize global scheduler."""
    global scheduler_service
    scheduler_service = SchedulerService(db=db)
    result = scheduler_service.initialize_scheduler()
    return result


def get_scheduler() -> Optional[SchedulerService]:
    """Get global scheduler instance."""
    return scheduler_service
