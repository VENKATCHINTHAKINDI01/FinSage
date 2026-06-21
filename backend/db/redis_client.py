"""
Redis client wrapper for caching, session storage, and distributed locks.
Handles connection pooling and error handling.
"""

import json
import logging
from typing import Any, Optional
import redis.asyncio as redis
from redis.asyncio.connection import ConnectionPool

from backend.config import settings

logger = logging.getLogger(__name__)

# Lazy-loaded Redis connection
_redis_client: Optional[redis.Redis] = None
_connection_pool: Optional[ConnectionPool] = None


async def get_redis() -> redis.Redis:
    """Get or create the Redis client."""
    global _redis_client, _connection_pool
    
    if _redis_client is None:
        logger.info(f"Connecting to Redis: {settings.redis.url}")
        try:
            _connection_pool = ConnectionPool.from_url(
                settings.redis.url,
                db=settings.redis.db,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True,
            )
            _redis_client = redis.Redis(connection_pool=_connection_pool)
            
            # Test connection
            await _redis_client.ping()
            logger.info("Redis connection established successfully")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    return _redis_client


async def close_redis() -> None:
    """Close Redis connection."""
    global _redis_client, _connection_pool
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
    if _connection_pool:
        await _connection_pool.disconnect()
        _connection_pool = None
    logger.info("Redis connection closed")


async def set_cache(
    key: str,
    value: Any,
    ttl: int = 3600,  # Default 1 hour
) -> bool:
    """
    Set value in Redis cache.
    
    Args:
        key: Cache key
        value: Any JSON-serializable value
        ttl: Time to live in seconds
    
    Returns:
        True if successful, False otherwise
    """
    try:
        client = await get_redis()
        if isinstance(value, dict):
            value = json.dumps(value)
        await client.setex(key, ttl, str(value))
        return True
    except Exception as e:
        logger.error(f"Cache set failed for key {key}: {e}")
        return False


async def get_cache(key: str) -> Optional[Any]:
    """
    Get value from Redis cache.
    
    Args:
        key: Cache key
    
    Returns:
        Cached value or None if not found
    """
    try:
        client = await get_redis()
        value = await client.get(key)
        if value and value.startswith("{"):
            return json.loads(value)
        return value
    except Exception as e:
        logger.error(f"Cache get failed for key {key}: {e}")
        return None


async def delete_cache(key: str) -> bool:
    """
    Delete value from Redis cache.
    
    Args:
        key: Cache key
    
    Returns:
        True if successful
    """
    try:
        client = await get_redis()
        await client.delete(key)
        return True
    except Exception as e:
        logger.error(f"Cache delete failed for key {key}: {e}")
        return False


async def clear_cache(pattern: str = "*") -> int:
    """
    Clear cache keys matching pattern.
    
    Args:
        pattern: Key pattern (e.g., "user_cache:*")
    
    Returns:
        Number of keys deleted
    """
    try:
        client = await get_redis()
        keys = await client.keys(pattern)
        if keys:
            return await client.delete(*keys)
        return 0
    except Exception as e:
        logger.error(f"Cache clear failed for pattern {pattern}: {e}")
        return 0


async def health_check_redis() -> bool:
    """
    Check if Redis is healthy.
    Returns True if connection successful.
    """
    try:
        client = await get_redis()
        await client.ping()
        return True
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return False


# Session-specific functions
async def set_session(
    session_id: str,
    user_id: str,
    ttl: int = 604800,  # 7 days
) -> bool:
    """Store session in Redis."""
    return await set_cache(f"session:{session_id}", {"user_id": user_id}, ttl)


async def get_session(session_id: str) -> Optional[dict]:
    """Retrieve session from Redis."""
    return await get_cache(f"session:{session_id}")


async def delete_session(session_id: str) -> bool:
    """Delete session from Redis."""
    return await delete_cache(f"session:{session_id}")


# User cache functions
async def cache_user(user_id: str, user_data: dict, ttl: int = 3600) -> bool:
    """Cache user data in Redis."""
    return await set_cache(f"user:{user_id}", user_data, ttl)


async def get_cached_user(user_id: str) -> Optional[dict]:
    """Get cached user data."""
    return await get_cache(f"user:{user_id}")


async def invalidate_user_cache(user_id: str) -> bool:
    """Invalidate user cache."""
    return await delete_cache(f"user:{user_id}")