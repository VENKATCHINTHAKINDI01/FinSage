"""
CRUD operations for User model.
Create, Read, Update, Delete functions.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
import logging

from backend.db.orm_models import User
from backend.db.redis_client import cache_user, invalidate_user_cache

logger = logging.getLogger(__name__)


async def create_user(
    session: AsyncSession,
    email: str,
    full_name: str,
    password_hash: str,
) -> User | None:
    """
    Create a new user.
    
    Args:
        session: AsyncSession
        email: User email (unique)
        full_name: User full name
        password_hash: Hashed password
    
    Returns:
        User object if successful, None if email already exists
    """
    try:
        user = User(
            email=email,
            full_name=full_name,
            password_hash=password_hash,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        
        logger.info(f"User created: {email}")
        return user
    except IntegrityError:
        await session.rollback()
        logger.warning(f"User creation failed: email already exists - {email}")
        return None
    except Exception as e:
        await session.rollback()
        logger.error(f"Error creating user: {e}")
        raise


async def get_user_by_id(
    session: AsyncSession,
    user_id: str,
) -> User | None:
    """
    Get user by ID.
    
    Args:
        session: AsyncSession
        user_id: User UUID
    
    Returns:
        User object or None if not found
    """
    try:
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Error fetching user {user_id}: {e}")
        return None


async def get_user_by_email(
    session: AsyncSession,
    email: str,
) -> User | None:
    """
    Get user by email.
    
    Args:
        session: AsyncSession
        email: User email
    
    Returns:
        User object or None if not found
    """
    try:
        result = await session.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Error fetching user by email {email}: {e}")
        return None


async def update_user(
    session: AsyncSession,
    user_id: str,
    **kwargs,
) -> User | None:
    """
    Update user fields.
    
    Args:
        session: AsyncSession
        user_id: User UUID
        **kwargs: Fields to update (full_name, email, is_active, etc.)
    
    Returns:
        Updated User object or None if not found
    """
    try:
        user = await get_user_by_id(session, user_id)
        if not user:
            return None
        
        for key, value in kwargs.items():
            if hasattr(user, key) and value is not None:
                setattr(user, key, value)
        
        await session.commit()
        await session.refresh(user)
        
        # Invalidate cache
        await invalidate_user_cache(user_id)
        
        logger.info(f"User updated: {user_id}")
        return user
    except Exception as e:
        await session.rollback()
        logger.error(f"Error updating user {user_id}: {e}")
        raise


async def delete_user(
    session: AsyncSession,
    user_id: str,
) -> bool:
    """
    Delete user (soft or hard delete).
    
    Args:
        session: AsyncSession
        user_id: User UUID
    
    Returns:
        True if successful, False otherwise
    """
    try:
        user = await get_user_by_id(session, user_id)
        if not user:
            return False
        
        # Soft delete: mark as inactive
        user.is_active = False
        await session.commit()
        
        # Invalidate cache
        await invalidate_user_cache(user_id)
        
        logger.info(f"User deleted (soft): {user_id}")
        return True
    except Exception as e:
        await session.rollback()
        logger.error(f"Error deleting user {user_id}: {e}")
        raise


async def list_users(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    active_only: bool = True,
) -> list[User]:
    """
    List users with pagination.
    
    Args:
        session: AsyncSession
        skip: Number of records to skip
        limit: Max records to return
        active_only: Only return active users
    
    Returns:
        List of User objects
    """
    try:
        query = select(User)
        if active_only:
            query = query.where(User.is_active == True)
        
        query = query.offset(skip).limit(limit)
        result = await session.execute(query)
        return result.scalars().all()
    except Exception as e:
        logger.error(f"Error listing users: {e}")
        return []


async def count_users(
    session: AsyncSession,
    active_only: bool = True,
) -> int:
    """
    Count total users.
    
    Args:
        session: AsyncSession
        active_only: Only count active users
    
    Returns:
        Total user count
    """
    try:
        from sqlalchemy import func
        query = select(func.count(User.id))
        if active_only:
            query = query.where(User.is_active == True)
        
        result = await session.execute(query)
        return result.scalar() or 0
    except Exception as e:
        logger.error(f"Error counting users: {e}")
        return 0


async def user_exists(
    session: AsyncSession,
    email: str,
) -> bool:
    """
    Check if user exists by email.
    
    Args:
        session: AsyncSession
        email: User email
    
    Returns:
        True if user exists, False otherwise
    """
    user = await get_user_by_email(session, email)
    return user is not None