"""
Service to manage user compliance audit histories and document checklists.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.orm_models import AuditHistory


class DocumentService:
    """
    Log and manage user compliance self-audits and external audit tracking.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.logger = logging.getLogger("service.document_service")
        
    async def log_audit_history(
        self,
        user_id: str,
        audit_type: str,
        findings: Dict[str, Any],
        action_taken: Optional[str] = None,
        status: str = "pending",
        saved_documents: Optional[List[str]] = None
    ) -> AuditHistory:
        """Create a new compliance audit history record."""
        try:
            audit = AuditHistory(
                user_id=user_id,
                audit_type=audit_type,
                audit_date=datetime.utcnow(),
                findings=findings,
                action_taken=action_taken,
                status=status,
                saved_documents=saved_documents or []
            )
            self.db.add(audit)
            await self.db.commit()
            self.logger.info(f"Audit log created: {audit_type} (Status: {status}) for user {user_id}")
            return audit
            
        except Exception as e:
            self.logger.error(f"Error logging audit history: {e}")
            await self.db.rollback()
            raise e
            
    async def resolve_audit_history(
        self,
        audit_id: str,
        action_taken: str,
        resolution_date: Optional[date] = None
    ) -> Optional[AuditHistory]:
        """Mark an audit finding as resolved with actions taken."""
        try:
            query = select(AuditHistory).where(AuditHistory.id == audit_id)
            result = await self.db.execute(query)
            audit = result.scalars().first()
            
            if audit:
                audit.status = "resolved"
                audit.action_taken = action_taken
                audit.resolution_date = resolution_date or date.today()
                audit.updated_at = datetime.utcnow()
                await self.db.commit()
                self.logger.info(f"Audit {audit_id} resolved successfully.")
                return audit
            return None
            
        except Exception as e:
            self.logger.error(f"Error resolving audit: {e}")
            await self.db.rollback()
            return None
            
    async def get_user_audit_history(self, user_id: str) -> List[AuditHistory]:
        """Fetch audit log list for a user."""
        query = select(AuditHistory).where(AuditHistory.user_id == user_id).order_by(AuditHistory.audit_date.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())
