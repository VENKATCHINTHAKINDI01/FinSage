"""
PostgreSQL database configuration and session management.
Uses SQLAlchemy with async support via asyncpg.
"""

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
    AsyncEngine,
)
from sqlalchemy.orm import declarative_base
from sqlalchemy import inspect, text
import logging

from backend.config import settings

logger = logging.getLogger(__name__)

# Base class for all ORM models
Base = declarative_base()

# Lazy-loaded engine (created on first use)
_engine: AsyncEngine | None = None
_async_session_maker: async_sessionmaker | None = None


async def get_engine() -> AsyncEngine:
    """Get or create the async SQLAlchemy engine."""
    global _engine
    if _engine is None:
        logger.info(f"Creating PostgreSQL engine: {settings.database.url}")
        _engine = create_async_engine(
            settings.database.url,
            echo=settings.database.echo,
            pool_size=settings.database.pool_size,
            max_overflow=settings.database.max_overflow,
            pool_pre_ping=True,  # Test connections before using
            pool_recycle=3600,   # Recycle connections after 1 hour
        )
        logger.info("PostgreSQL engine created successfully")
    return _engine


async def get_session_maker() -> async_sessionmaker:
    """Get or create the async session maker."""
    global _async_session_maker
    if _async_session_maker is None:
        engine = await get_engine()
        _async_session_maker = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
    return _async_session_maker


async def get_session() -> AsyncSession:
    """
    Dependency for FastAPI route handlers.
    Usage:
        async def my_route(session: AsyncSession = Depends(get_session)):
            ...
    """
    session_maker = await get_session_maker()
    async with session_maker() as session:
        yield session


async def init_db() -> None:
    """
    Initialize database: create all tables.
    Call this in app startup.
    """
    engine = await get_engine()
    async with engine.begin() as conn:
        logger.info("Creating database tables...")
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully")


async def health_check_db() -> bool:
    """
    Check if database is healthy.
    Returns True if connection successful, False otherwise.
    """
    try:
        engine = await get_engine()
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False


async def close_db() -> None:
    """
    Close database connections.
    Call this in app shutdown.
    """
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None
        logger.info("Database connections closed")


def get_table_names(engine_or_inspector) -> list[str]:
    """Get list of all table names in the database."""
    if isinstance(engine_or_inspector, AsyncEngine):
        raise ValueError("Use sync engine for inspection. This is a utility function.")
    inspector = inspect(engine_or_inspector)
    return inspector.get_table_names()