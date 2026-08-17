"""
FastAPI dependency functions for authentication.
Used with Depends() in route handlers to protect endpoints.
"""

import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.crud.refresh_sessions import load_check_store
from backend.db.crud.users import get_user_by_id
from backend.db.postgres import get_session
from backend.models import UserResponse
from backend.security.jwt_handler import verify_token
from backend.security.sessions import TokenRejected, assert_usable

logger = logging.getLogger(__name__)

# HTTP Bearer token scheme
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    """
    Extract and validate JWT token from Authorization header.
    Return the current authenticated user.
    """
    token = credentials.credentials

    # Verify token validity
    payload = verify_token(token, token_type="access")
    if not payload:
        logger.warning("Invalid or expired token provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("user_id")
    if not user_id:
        logger.warning("Token payload is missing user_id")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # PRD-002: the revocation check `get_current_user` never made. A logged-out
    # or reuse-revoked family must stop working immediately, not at the token's
    # natural 15-minute expiry.
    family = payload.get("family")
    if family:
        check_store = await load_check_store(session, family=str(family), jti=payload.get("jti"))
        try:
            assert_usable(payload, check_store)
        except TokenRejected:
            logger.warning("Rejected a revoked/reused session for user %s", user_id)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            ) from None

    user = await get_user_by_id(session, user_id)
    if not user:
        logger.warning(f"User not found: {user_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        logger.warning(f"User account inactive: {user_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    return UserResponse.model_validate(user)


async def get_current_user_id(
    user: UserResponse = Depends(get_current_user),
) -> str:
    """
    Get just the current user's ID.
    """
    return user.id


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        HTTPBearer(auto_error=False)
    ),
    session: AsyncSession = Depends(get_session),
) -> UserResponse | None:
    """
    Optional authentication — endpoint works with or without token.
    """
    if not credentials:
        return None
    try:
        token = credentials.credentials
        payload = verify_token(token, token_type="access")
        if not payload:
            return None
        user_id = payload.get("user_id")
        if not user_id:
            return None
        user = await get_user_by_id(session, user_id)
        if not user or not user.is_active:
            return None
        return UserResponse.model_validate(user)
    except Exception:
        return None
