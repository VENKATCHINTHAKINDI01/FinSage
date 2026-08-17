"""
JWT handler for encoding, decoding, and validating JSON Web Tokens.
"""

import logging
from datetime import timedelta
from typing import Any

import jwt

from backend.config import settings
from backend.security.sessions import new_id, now_utc

logger = logging.getLogger(__name__)


def create_token(
    user_id: str,
    token_type: str = "access",
    expires_delta: timedelta | None = None,
    *,
    jti: str | None = None,
    family: str | None = None,
) -> str:
    """Generate a JWT token for a given user ID and token type.

    `jti` and `family` are PRD-002. Without them a token has no handle: it
    cannot be revoked, and `get_current_user` has nothing to check against the
    sessions table. Both default to a fresh id so a caller that forgets still
    produces a revocable token rather than an anonymous one.

    Times are timezone-aware. `datetime.utcnow()` returns a NAIVE datetime that
    claims to be timezone.utc, which compares wrongly against anything aware.
    """
    issued = now_utc()
    if expires_delta:
        expire = issued + expires_delta
    elif token_type == "access":
        expire = issued + timedelta(minutes=settings.auth.access_token_expire_minutes)
    else:
        expire = issued + timedelta(days=settings.auth.refresh_token_expire_days)

    payload = {
        "sub": user_id,
        "user_id": user_id,
        "type": token_type,
        "jti": jti or new_id(),
        "family": family or new_id(),
        "exp": expire,
        "iat": issued,
    }

    encoded_jwt = jwt.encode(
        payload,
        settings.auth.secret_key,
        algorithm=settings.auth.algorithm
    )
    return encoded_jwt


def create_access_token(
    user_id: str,
    expires_delta: timedelta | None = None,
    *,
    jti: str | None = None,
    family: str | None = None,
) -> str:
    """Generate an access token."""
    return create_token(
        user_id, token_type="access", expires_delta=expires_delta,
        jti=jti, family=family,
    )


def create_refresh_token(
    user_id: str,
    expires_delta: timedelta | None = None,
    *,
    jti: str | None = None,
    family: str | None = None,
) -> str:
    """Generate a refresh token."""
    return create_token(
        user_id, token_type="refresh", expires_delta=expires_delta,
        jti=jti, family=family,
    )


def verify_token(token: str, token_type: str = "access") -> dict[str, Any] | None:
    """
    Verify and decode a JWT token.
    Ensures token type matches and token is not expired.
    """
    try:
        payload = jwt.decode(
            token,
            settings.auth.secret_key,
            algorithms=[settings.auth.algorithm]
        )

        # Verify token type matches
        if payload.get("type") != token_type:
            logger.warning(f"Token type mismatch: expected {token_type}, got {payload.get('type')}")
            return None

        return payload

    except jwt.ExpiredSignatureError:
        logger.warning("Token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {e}")
        return None
    except Exception as e:
        logger.error(f"Error verifying token: {e}")
        return None
