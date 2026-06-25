"""
Authentication endpoints for user registration and login.
Routes: /api/v1/auth/register, /api/v1/auth/login, /api/v1/auth/refresh
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from backend.db.postgres import get_session
from backend.security.dependencies import get_current_user
from backend.db.crud.users import create_user, get_user_by_email, user_exists
from backend.db.crud.sessions import create_session
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
from backend.config import settings
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
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
    
    # Hash password
    password_hash = hash_password(user_data.password)
    
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
    return UserResponse.from_orm(user)


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
    
    # Verify password
    if not verify_password(credentials.password, user.password_hash):
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
    
    # Generate tokens
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    
    # Create session record in database (optional, for audit trail)
    expires_at = datetime.utcnow() + timedelta(
        minutes=settings.auth.access_token_expire_minutes
    )
    await create_session(
        session,
        user_id=user.id,
        token=access_token,
        expires_at=expires_at,
    )
    
    logger.info(f"User logged in successfully: {credentials.email}")
    
    return AuthTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.auth.access_token_expire_minutes * 60,  # Convert to seconds
    )


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
            "refresh_token": "eyJhbGc...",
            "token_type": "bearer",
            "expires_in": 900
        }
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
    
    # Verify user still exists and is active
    user = await get_user_by_id(session, user_id)
    if not user or not user.is_active:
        logger.warning(f"Token refresh failed: user not found or inactive - {user_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or account inactive",
        )
    
    # Generate new access token
    new_access_token = create_access_token(user_id)
    
    logger.info(f"Token refreshed for user: {user_id}")
    
    return AuthTokenResponse(
        access_token=new_access_token,
        refresh_token=refresh_token,  # Return same refresh token
        token_type="bearer",
        expires_in=settings.auth.access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: UserResponse = Depends(get_current_user),
) -> UserResponse:
    """
    Get current authenticated user details.
    """
    return current_user


# Helper import needed
from backend.db.crud.users import get_user_by_id