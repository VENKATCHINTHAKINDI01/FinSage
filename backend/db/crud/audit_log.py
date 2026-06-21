"""
CRUD operations for AuditLog model.
"""

from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.orm_models import AuditLog


async def create_audit_log(
    db: AsyncSession,
    user_id: Optional[str],
    action: str,
    entity: str,
    entity_id: Optional[str] = None,
    changes: Optional[str] = None,
    ip_address: Optional[str] = None
) -> AuditLog:
    """Create a new audit log record."""
    db_log = AuditLog(
        user_id=user_id,
        action=action,
        entity=entity,
        entity_id=entity_id,
        changes=changes,
        ip_address=ip_address
    )
    db.add(db_log)
    await db.commit()
    return db_log


async def get_audit_logs(
    db: AsyncSession,
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
) -> List[AuditLog]:
    """Retrieve audit logs with optional filters."""
    query = select(AuditLog)
    if user_id:
        query = query.where(AuditLog.user_id == user_id)
    if action:
        query = query.where(AuditLog.action == action)
    
    query = query.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    return list(result.scalars().all())
