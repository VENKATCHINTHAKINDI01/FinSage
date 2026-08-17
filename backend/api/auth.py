"""
Authentication endpoints for user registration and login.
Routes: /api/v1/auth/register, /api/v1/auth/login, /api/v1/auth/refresh
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.postgres import get_session
from backend.security.dependencies import get_current_user
from backend.db.crud.users import create_user, get_user_by_email, get_user_by_id, user_exists
from backend.db.crud.sessions import create_session
from backend.db.crud.refresh_sessions import load_family_store, persist_new_record, persist_store
from backend.models import (
    UserCreate,
    UserResponse,
    UserLogin,
    AuthTokenResponse,
)
from backend.security.password import hash_password, verify_password, is_password_strong
from backend.security.jwt_handler import (
    create_access_token,
    create_refresh_token,
    verify_token,
)
from backend.security.sessions import (
    InMemorySessions,
    TokenRejected,
    logout as end_session,
    rotate,
    start_session,
)
from backend.config import settings
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])

REFRESH_LIFETIME = timedelta(days=settings.auth.refresh_token_expire_days)


async def _issue_tokens(session: AsyncSession, user_id: str) -> AuthTokenResponse:
    """PRD-002: every login opens a fresh rotation family and both tokens
    carry it, so the revocation check in `get_current_user` and a future
    refresh both have a handle to check against."""
    record = start_session(user_id, InMemorySessions(), lifetime=REFRESH_LIFETIME)
    await persist_new_record(session, record)

    access_token = create_access_token(user_id, jti=record.jti, family=record.family)
    refresh_token = create_refresh_token(user_id, jti=record.jti, family=record.family)

    return AuthTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.auth.access_token_expire_minutes * 60,
    )


@router.post("/register", response_model=AuthTokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    session: AsyncSession = Depends(get_session),
) -> AuthTokenResponse:
    """
    Register a new user account.
    
    Parameters:
    - email: Valid email address (unique)
    - full_name: User's full name (1-255 chars)
    - password: Min 8 chars, uppercase, lowercase, digit, special char
    
    Returns:
    - User object with id, email, full_name, created_at
    
    Errors:
    - 400: Email already exists
    - 400: Invalid password
    - 422: Validation error (missing fields, wrong types)
    
    Example:
        POST /api/v1/auth/register
        {
            "email": "user@example.com",
            "full_name": "John Doe",
            "password": "Secure@Pass123"
        }
        
        Response:
        {
            "id": "abc-123",
            "email": "user@example.com",
            "full_name": "John Doe",
            "is_active": true,
            "created_at": "2025-06-05T10:30:00Z",
            "updated_at": "2025-06-05T10:30:00Z"
        }
    """
    # Check if user already exists
    if await user_exists(session, user_data.email):
        logger.warning(f"Registration failed: email already exists - {user_data.email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    
    # Validate password strength
    is_strong, error_msg = is_password_strong(user_data.password)
    if not is_strong:
        logger.warning(f"Registration failed: weak password - {error_msg}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg,
        )
    
    # PRD-007 bugfix: bcrypt is deliberately slow (that is the point of a
    # password hash) and passlib's `hash()` is synchronous CPU-bound work —
    # calling it directly here blocks the single-threaded event loop for the
    # full hash duration, serializing every concurrent request on the process,
    # not just registrations. A real load test at 20 concurrent registrations
    # measured a 4.6s p95 before this fix (20 hashes queued one after another
    # on one core) against ~30ms for an equally-loaded endpoint that never
    # blocks the loop. `asyncio.to_thread` moves the hash off the loop so
    # concurrent requests actually run concurrently.
    password_hash = await asyncio.to_thread(hash_password, user_data.password)

    # Create user in database
    user = await create_user(
        session,
        email=user_data.email,
        full_name=user_data.full_name,
        password_hash=password_hash,
    )
    
    if not user:
        logger.error(f"Failed to create user: {user_data.email}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user account",
        )
    
    logger.info(f"User registered successfully: {user.email}")

    # Generate tokens for immediate login after registration
    tokens = await _issue_tokens(session, str(user.id))
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.auth.access_token_expire_minutes
    )
    await create_session(
        session,
        user_id=user.id,
        token=tokens.access_token,
        expires_at=expires_at,
    )

    return tokens


@router.post("/login", response_model=AuthTokenResponse)
async def login(
    credentials: UserLogin,
    session: AsyncSession = Depends(get_session),
) -> AuthTokenResponse:
    """
    Authenticate user and return access + refresh tokens.
    
    Parameters:
    - email: User email
    - password: User password
    
    Returns:
    - access_token: JWT token (15 min expiry)
    - refresh_token: JWT token (7 day expiry)
    - token_type: "bearer"
    - expires_in: Seconds until access token expires
    
    Errors:
    - 401: Invalid email or password
    - 403: Account inactive
    
    Example:
        POST /api/v1/auth/login
        {
            "email": "user@example.com",
            "password": "Secure@Pass123"
        }
        
        Response:
        {
            "access_token": "eyJhbGc...",
            "refresh_token": "eyJhbGc...",
            "token_type": "bearer",
            "expires_in": 900
        }
    """
    # Find user by email
    user = await get_user_by_email(session, credentials.email)
    
    # Check if user exists
    if not user:
        logger.warning(f"Login failed: user not found - {credentials.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    
    # PRD-007 bugfix: same event-loop-blocking issue as the register path —
    # verify() runs the same bcrypt cost, off the loop via to_thread.
    if not await asyncio.to_thread(verify_password, credentials.password, user.password_hash):
        logger.warning(f"Login failed: invalid password - {credentials.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    
    # Check if account is active
    if not user.is_active:
        logger.warning(f"Login failed: account inactive - {credentials.email}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )
    
    # Generate tokens — PRD-002: opens a fresh rotation family
    tokens = await _issue_tokens(session, str(user.id))

    # Create session record in database (optional, for audit trail)
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.auth.access_token_expire_minutes
    )
    await create_session(
        session,
        user_id=user.id,
        token=tokens.access_token,
        expires_at=expires_at,
    )

    logger.info(f"User logged in successfully: {credentials.email}")

    return tokens


@router.post("/refresh", response_model=AuthTokenResponse)
async def refresh_token(
    refresh_token: str,
    session: AsyncSession = Depends(get_session),
) -> AuthTokenResponse:
    """
    Get a new access token using a refresh token.
    
    Parameters:
    - refresh_token: Valid refresh token from login
    
    Returns:
    - New access_token
    - refresh_token (same one)
    - token_type
    - expires_in
    
    Errors:
    - 401: Invalid or expired refresh token
    
    Example:
        POST /api/v1/auth/refresh
        {
            "refresh_token": "eyJhbGc..."
        }

        Response:
        {
            "access_token": "eyJhbGc...",
            "refresh_token": "eyJhbGc...",   # a NEW token — the old one is now dead
            "token_type": "bearer",
            "expires_in": 900
        }

    PRD-002: the refresh token is single use. Presenting it a second time (the
    signature that it has been stolen) revokes every token descended from the
    same login, this one included — the client must sign in again, and so must
    the thief.
    """
    # Verify refresh token
    payload = verify_token(refresh_token, token_type="refresh")
    if not payload:
        logger.warning("Token refresh failed: invalid refresh token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user_id: str = payload.get("user_id")
    jti = payload.get("jti")
    if not jti:
        # Minted before rotation existed. Cannot be tracked or revoked — treat
        # it the same as any other rejection, not as a free pass.
        logger.warning(f"Token refresh failed: no jti - {user_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    # Verify user still exists and is active
    user = await get_user_by_id(session, user_id)
    if not user or not user.is_active:
        logger.warning(f"Token refresh failed: user not found or inactive - {user_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or account inactive",
        )

    store = await load_family_store(session, jti)
    try:
        successor = rotate(jti, store, lifetime=REFRESH_LIFETIME)
    except TokenRejected as exc:
        # One exception type, one response for every cause (unknown / reused /
        # revoked / expired) — the client must not be able to tell them apart.
        logger.warning(f"Token refresh rejected for user {user_id}: {exc.reason}")
        await persist_store(session, store)  # e.g. reuse revoked the family
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        ) from None

    await persist_store(session, store)

    new_access_token = create_access_token(user_id, jti=successor.jti, family=successor.family)
    new_refresh_token = create_refresh_token(user_id, jti=successor.jti, family=successor.family)

    logger.info(f"Token refreshed for user: {user_id}")

    return AuthTokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        expires_in=settings.auth.access_token_expire_minutes * 60,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    refresh_token: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    """
    End the session the refresh token belongs to.

    PRD-002: this revokes the whole family, not just the presented token — a
    client that logs out after refreshing should not leave the rotated-out
    predecessor's family alive.
    """
    payload = verify_token(refresh_token, token_type="refresh")
    jti = payload.get("jti") if payload else None
    if not jti:
        # Nothing to revoke. Logging out with an already-invalid token is a
        # no-op, not an error — the caller's goal (no live session) is met.
        return None

    store = await load_family_store(session, jti)
    end_session(jti, store)
    await persist_store(session, store)
    return None


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: UserResponse = Depends(get_current_user),
) -> UserResponse:
    """
    Get current authenticated user details.
    """
    return current_user
