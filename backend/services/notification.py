"""
Service to dispatch notifications and manage user channel preferences.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.orm_models import Notification, NotificationPreference


class NotificationService:
    """
    Handle notification routing, preferences validation, and dispatch tracking.
    Supported channels: email, telegram, sms
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.logger = logging.getLogger("service.notification")
        
    async def send_notification(
        self,
        user_id: str,
        notification_type: str,
        channel: str,
        recipient: str,
        subject: Optional[str],
        message: str,
        data: Optional[Dict[str, Any]] = None
    ) -> Notification:
        """
        Validate user preferences and dispatch notification.
        """
        try:
            # Check preferences first
            pref_query = (
                select(NotificationPreference)
                .where(NotificationPreference.user_id == user_id)
                .where(NotificationPreference.channel == channel)
            )
            pref_res = await self.db.execute(pref_query)
            preference = pref_res.scalars().first()
            
            # If preference exists and is disabled, do not send
            if preference and not preference.enabled:
                self.logger.info(f"Notification blocked: Channel {channel} is disabled for user {user_id}")
                notification = Notification(
                    user_id=user_id,
                    notification_type=notification_type,
                    channel=channel,
                    recipient=recipient,
                    subject=subject,
                    message=message,
                    data=data,
                    status="failed",
                    error_message="Channel disabled by user preferences"
                )
                self.db.add(notification)
                await self.db.commit()
                return notification
            
            # Create pending record
            notification = Notification(
                user_id=user_id,
                notification_type=notification_type,
                channel=channel,
                recipient=recipient,
                subject=subject,
                message=message,
                data=data,
                status="pending",
                retry_count=0
            )
            self.db.add(notification)
            await self.db.flush()  # Populates id
            
            # Simulate dispatch
            success = True
            error_msg = None
            
            try:
                # Production hook: actually dispatch via Twilio / Resend API / Telegram bot
                self.logger.info(f"Dispatching {channel} notification to {recipient}...")
            except Exception as e:
                success = False
                error_msg = str(e)
                
            if success:
                notification.status = "sent"
                notification.sent_at = datetime.utcnow()
                self.logger.info(f"Notification {notification.id} sent successfully via {channel}")
            else:
                notification.status = "failed"
                notification.error_message = error_msg
                self.logger.warning(f"Notification {notification.id} failed: {error_msg}")
                
            await self.db.commit()
            return notification
            
        except Exception as e:
            self.logger.error(f"Error sending notification: {e}", exc_info=True)
            await self.db.rollback()
            raise e
            
    async def set_user_preference(
        self,
        user_id: str,
        channel: str,
        enabled: bool,
        frequency: str = "as_needed",
        preferred_time: Optional[time] = None,
        notification_types: Optional[List[str]] = None
    ) -> NotificationPreference:
        """
        Save or update notification channel preference.
        """
        try:
            query = (
                select(NotificationPreference)
                .where(NotificationPreference.user_id == user_id)
                .where(NotificationPreference.channel == channel)
            )
            res = await self.db.execute(query)
            preference = res.scalars().first()
            
            if preference:
                preference.enabled = enabled
                preference.frequency = frequency
                preference.preferred_time = preferred_time
                preference.notification_types = notification_types
                preference.updated_at = datetime.utcnow()
            else:
                preference = NotificationPreference(
                    user_id=user_id,
                    channel=channel,
                    enabled=enabled,
                    frequency=frequency,
                    preferred_time=preferred_time,
                    notification_types=notification_types
                )
                self.db.add(preference)
                
            await self.db.commit()
            self.logger.info(f"Saved preference: {channel} enabled={enabled} for user {user_id}")
            return preference
            
        except Exception as e:
            self.logger.error(f"Error saving preference: {e}")
            await self.db.rollback()
            raise e
            
    async def get_user_preferences(self, user_id: str) -> List[NotificationPreference]:
        """Fetch all channel preferences for a user."""
        query = select(NotificationPreference).where(NotificationPreference.user_id == user_id)
        result = await self.db.execute(query)
        return list(result.scalars().all())
