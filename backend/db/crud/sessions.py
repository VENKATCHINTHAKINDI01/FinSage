"""
CRUD operations for Session model.
Manages user authentication sessions and tokens.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.sql import and_
from datetime import datetime, timedelta
import logging

from backend.db.orm_models import Session
from backend.db.redis_client import set_session, get_session as get_redis_session, delete_session as delete_redis_session

logger = logging.getLogger(__name__)


async def create_session(
    session: AsyncSession,
    user_id: str,
    token: str,
    expires_at: datetime,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> Session | None:
    """
    Create a new session.
    
    Args:
        session: AsyncSession
        user_id: User UUID
        token: JWT token
        expires_at: Token expiration datetime
        ip_address: User IP address
        user_agent: User browser/agent string
    
    Returns:
        Session object if successful
    """
    try:
        db_session = Session(
            user_id=user_id,
            token=token,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        session.add(db_session)
        await session.commit()
        await session.refresh(db_session)
        
        # Cache in Redis (7 days TTL)
        ttl = int((expires_at - datetime.utcnow()).total_seconds())
        await set_session(db_session.id, user_id, ttl)
        
        logger.info(f"Session created for user: {user_id}")
        return db_session
    except Exception as e:
        await session.rollback()
        logger.error(f"Error creating session: {e}")
        raise


async def get_session_by_token(
    session: AsyncSession,
    token: str,
) -> Session | None:
    """
    Get session by token.
    
    Args:
        session: AsyncSession
        token: JWT token
    
    Returns:
        Session object or None if not found or expired
    """
    try:
        result = await session.execute(
            select(Session).where(
                and_(
                    Session.token == token,
                    Session.expires_at > datetime.utcnow(),
                )
            )
        )
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Error fetching session by token: {e}")
        return None


async def get_session_by_id(
    session: AsyncSession,
    session_id: str,
) -> Session | None:
    """
    Get session by ID.
    
    Args:
        session: AsyncSession
        session_id: Session UUID
    
    Returns:
        Session object or None if not found
    """
    try:
        result = await session.execute(
            select(Session).where(Session.id == session_id)
        )
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Error fetching session {session_id}: {e}")
        return None


async def get_user_sessions(
    session: AsyncSession,
    user_id: str,
    active_only: bool = True,
) -> list[Session]:
    """
    Get all sessions for a user.
    
    Args:
        session: AsyncSession
        user_id: User UUID
        active_only: Only return non-expired sessions
    
    Returns:
        List of Session objects
    """
    try:
        query = select(Session).where(Session.user_id == user_id)
        
        if active_only:
            query = query.where(Session.expires_at > datetime.utcnow())
        
        result = await session.execute(query)
        return result.scalars().all()
    except Exception as e:
        logger.error(f"Error fetching sessions for user {user_id}: {e}")
        return []


async def delete_session(
    session: AsyncSession,
    session_id: str,
) -> bool:
    """
    Delete a session.
    
    Args:
        session: AsyncSession
        session_id: Session UUID
    
    Returns:
        True if successful, False otherwise
    """
    try:
        db_session = await get_session_by_id(session, session_id)
        if not db_session:
            return False
        
        await session.delete(db_session)
        await session.commit()
        
        # Delete from Redis
        await delete_redis_session(session_id)
        
        logger.info(f"Session deleted: {session_id}")
        return True
    except Exception as e:
        await session.rollback()
        logger.error(f"Error deleting session {session_id}: {e}")
        raise


async def delete_all_user_sessions(
    session: AsyncSession,
    user_id: str,
) -> int:
    """
    Delete all sessions for a user (logout all devices).
    
    Args:
        session: AsyncSession
        user_id: User UUID
    
    Returns:
        Number of sessions deleted
    """
    try:
        sessions = await get_user_sessions(session, user_id, active_only=False)
        count = 0
        
        for s in sessions:
            await session.delete(s)
            await delete_redis_session(s.id)
            count += 1
        
        await session.commit()
        logger.info(f"Deleted {count} sessions for user: {user_id}")
        return count
    except Exception as e:
        await session.rollback()
        logger.error(f"Error deleting sessions for user {user_id}: {e}")
        raise


async def cleanup_expired_sessions(
    session: AsyncSession,
) -> int:
    """
    Delete all expired sessions (housekeeping).
    
    Args:
        session: AsyncSession
    
    Returns:
        Number of sessions deleted
    """
    try:
        result = await session.execute(
            select(Session).where(Session.expires_at <= datetime.utcnow())
        )
        expired_sessions = result.scalars().all()
        count = len(expired_sessions)
        
        for s in expired_sessions:
            await session.delete(s)
            await delete_redis_session(s.id)
        
        await session.commit()
        logger.info(f"Cleaned up {count} expired sessions")
        return count
    except Exception as e:
        await session.rollback()
        logger.error(f"Error cleaning up expired sessions: {e}")
        raise


async def is_session_valid(
    session: AsyncSession,
    token: str,
) -> bool:
    """
    Check if session is valid (exists and not expired).
    
    Args:
        session: AsyncSession
        token: JWT token
    
    Returns:
        True if valid, False otherwise
    """
    db_session = await get_session_by_token(session, token)
    return db_session is not None