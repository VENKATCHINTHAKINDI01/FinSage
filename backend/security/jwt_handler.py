"""
JWT handler for encoding, decoding, and validating JSON Web Tokens.
"""

import jwt
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from backend.config import settings

logger = logging.getLogger(__name__)


def create_token(
    user_id: str,
    token_type: str = "access",
    expires_delta: Optional[timedelta] = None
) -> str:
    """Generate a JWT token for a given user ID and token type."""
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        if token_type == "access":
            expire = datetime.utcnow() + timedelta(minutes=settings.auth.access_token_expire_minutes)
        else:
            expire = datetime.utcnow() + timedelta(days=settings.auth.refresh_token_expire_days)
            
    payload = {
        "sub": user_id,
        "user_id": user_id,
        "type": token_type,
        "exp": expire,
        "iat": datetime.utcnow()
    }
    
    encoded_jwt = jwt.encode(
        payload,
        settings.auth.secret_key,
        algorithm=settings.auth.algorithm
    )
    return encoded_jwt


def create_access_token(user_id: str, expires_delta: Optional[timedelta] = None) -> str:
    """Generate an access token."""
    return create_token(user_id, token_type="access", expires_delta=expires_delta)


def create_refresh_token(user_id: str, expires_delta: Optional[timedelta] = None) -> str:
    """Generate a refresh token."""
    return create_token(user_id, token_type="refresh", expires_delta=expires_delta)


def verify_token(token: str, token_type: str = "access") -> Optional[Dict[str, Any]]:
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
