"""
Password utility functions for hashing and validation.
"""

import re
from typing import Tuple, Optional
from passlib.context import CryptContext

# Setup password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plain password matches hash."""
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False


def is_password_strong(password: str) -> Tuple[bool, Optional[str]]:
    """
    Check if password is strong:
    - Min 8 characters
    - At least 1 uppercase letter
    - At least 1 lowercase letter
    - At least 1 digit
    - At least 1 special character
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
        
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter."
        
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter."
        
    if not re.search(r"\d", password):
        return False, "Password must contain at least one digit."
        
    if not re.search(r"[!@#\$%\^&\*\(\),\.\?\":\{\}\|<>]", password):
        return False, "Password must contain at least one special character."
        
    return True, None
