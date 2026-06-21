"""
Service to manage compliance red flags and scheduled tasks execution logs.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.orm_models import RedFlagLog, ScheduledTask


class AlertService:
    """
    Log and resolve red flags, and manage scheduled automated runs.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.logger = logging.getLogger("service.alert_service")
        
    async def log_red_flag(
        self,
        user_id: str,
        flag_name: str,
        severity: str,
        description: str,
        action_required: Optional[str] = None
    ) -> RedFlagLog:
        """Create a new compliance red flag log."""
        try:
            flag = RedFlagLog(
                user_id=user_id,
                flag_name=flag_name,
                severity=severity,
                description=description,
                action_required=action_required,
                resolved=False
            )
            self.db.add(flag)
            await self.db.commit()
            self.logger.info(f"Red flag logged: {flag_name} (Severity: {severity}) for user {user_id}")
            return flag
            
        except Exception as e:
            self.logger.error(f"Error logging red flag: {e}")
            await self.db.rollback()
            raise e
            
    async def resolve_red_flag(self, flag_id: str) -> Optional[RedFlagLog]:
        """Mark a red flag as resolved."""
        try:
            query = select(RedFlagLog).where(RedFlagLog.id == flag_id)
            result = await self.db.execute(query)
            flag = result.scalars().first()
            
            if flag:
                flag.resolved = True
                flag.resolved_date = datetime.utcnow()
                await self.db.commit()
                self.logger.info(f"Red flag resolved: {flag.flag_name} for user {flag.user_id}")
                return flag
            return None
            
        except Exception as e:
            self.logger.error(f"Error resolving red flag: {e}")
            await self.db.rollback()
            return None
            
    async def create_scheduled_task(
        self,
        task_name: str,
        task_type: str,
        schedule: str,
        is_active: bool = True
    ) -> ScheduledTask:
        """Register a new scheduled task in the system."""
        try:
            task = ScheduledTask(
                task_name=task_name,
                task_type=task_type,
                schedule=schedule,
                is_active=is_active,
                next_run=datetime.utcnow() + timedelta(days=1), # default offset
                execution_log=[]
            )
            self.db.add(task)
            await self.db.commit()
            self.logger.info(f"Registered scheduled task: {task_name} ({schedule})")
            return task
            
        except Exception as e:
            self.logger.error(f"Error registering task: {e}")
            await self.db.rollback()
            raise e
            
    async def execute_scheduled_task(
        self,
        task_id: str,
        status: str = "success",
        log_message: Optional[str] = None
    ) -> Optional[ScheduledTask]:
        """Log a scheduled task run execution and update its schedule properties."""
        try:
            query = select(ScheduledTask).where(ScheduledTask.id == task_id)
            result = await self.db.execute(query)
            task = result.scalars().first()
            
            if task:
                task.last_run = datetime.utcnow()
                task.next_run = datetime.utcnow() + timedelta(days=1)  # simple daily reschedule
                
                # Append to logs
                run_log = {
                    "executed_at": task.last_run.isoformat(),
                    "status": status,
                    "message": log_message or "Execution completed successfully"
                }
                
                current_logs = list(task.execution_log) if task.execution_log else []
                current_logs.append(run_log)
                task.execution_log = current_logs
                
                await self.db.commit()
                self.logger.info(f"Executed scheduled task: {task.task_name}. Status: {status}")
                return task
            return None
            
        except Exception as e:
            self.logger.error(f"Error executing task: {e}")
            await self.db.rollback()
            return None
            
    async def get_user_red_flag_history(self, user_id: str) -> List[RedFlagLog]:
        """Fetch all resolved or active red flags for a user."""
        query = select(RedFlagLog).where(RedFlagLog.user_id == user_id).order_by(RedFlagLog.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())
