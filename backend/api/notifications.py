"""
Notifications API Endpoints - Step 10
"""

import asyncio
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.security.dependencies import get_current_user
from backend.db.postgres import get_session
from backend.services.notification import NotificationService

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


class NotificationPreferencesRequest(BaseModel):
    """Set notification preferences"""
    channel: str  # email, telegram
    enabled: bool
    frequency: str  # daily, weekly, monthly, as_needed
    preferred_time: str = None  # HH:MM


@router.post("/preferences")
async def set_notification_preferences(
    request: NotificationPreferencesRequest,
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """Set user notification preferences"""
    try:
        notification_service = NotificationService(db=session)
        
        result = await notification_service.set_user_preferences(
            user_id=current_user.id,
            channel=request.channel,
            enabled=request.enabled,
            frequency=request.frequency,
            preferred_time=request.preferred_time
        )
        
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/preferences")
async def get_notification_preferences(
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """Get user notification preferences"""
    try:
        notification_service = NotificationService(db=session)
        
        result = await notification_service.get_user_preferences(current_user.id)
        
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_notification_history(
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """Get user notification history"""
    try:
        notification_service = NotificationService(db=session)
        
        history = notification_service.get_notification_history(current_user.id, limit=20)
        if asyncio.iscoroutine(history):
            history = await history
        
        return {
            "success": True,
            "total": len(history),
            "notifications": history
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
