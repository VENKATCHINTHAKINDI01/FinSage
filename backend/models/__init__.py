"""
Pydantic models for data validation and serialization.
Used for API request/response bodies.
"""

from pydantic import BaseModel, EmailStr, Field, condecimal
from datetime import datetime
from typing import Optional
from decimal import Decimal


# ==================== USER MODELS ====================

class UserBase(BaseModel):
    """Base user model with common fields."""
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=255)


class UserCreate(UserBase):
    """Model for user registration."""
    password: str = Field(..., min_length=8, max_length=255)


class UserLogin(BaseModel):
    """Model for user login."""
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    """Model for updating user profile."""
    full_name: Optional[str] = Field(None, max_length=255)
    email: Optional[EmailStr] = None


class UserResponse(UserBase):
    """Model for user response (no password)."""
    id: str
    created_at: datetime
    updated_at: datetime
    is_active: bool = True
    
    class Config:
        from_attributes = True  # For SQLAlchemy model conversion


# ==================== FINANCIAL PROFILE MODELS ====================

class FinancialProfileBase(BaseModel):
    """Base financial profile model."""
    annual_income: condecimal(gt=0, decimal_places=2)
    monthly_expenses: condecimal(ge=0, decimal_places=2)
    investment_amount: condecimal(ge=0, decimal_places=2) = Decimal("0")
    employment_type: str = Field(
        default="individual",
        pattern="^(individual|freelancer|salaried|business|retired)$"
    )
    financial_goal: Optional[str] = Field(None, max_length=500)


class FinancialProfileCreate(FinancialProfileBase):
    """Model for creating financial profile."""
    pass


class FinancialProfileUpdate(BaseModel):
    """Model for updating financial profile."""
    annual_income: Optional[condecimal(gt=0, decimal_places=2)] = None
    monthly_expenses: Optional[condecimal(ge=0, decimal_places=2)] = None
    investment_amount: Optional[condecimal(ge=0, decimal_places=2)] = None
    employment_type: Optional[str] = None
    financial_goal: Optional[str] = Field(None, max_length=500)


class FinancialProfileResponse(FinancialProfileBase):
    """Model for financial profile response."""
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# ==================== SESSION MODELS ====================

class SessionCreate(BaseModel):
    """Model for session creation."""
    user_id: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class SessionResponse(BaseModel):
    """Model for session response."""
    id: str
    user_id: str
    token: str
    expires_at: datetime
    created_at: datetime
    ip_address: Optional[str] = None
    
    class Config:
        from_attributes = True


# ==================== AUTH MODELS ====================

class AuthTokenResponse(BaseModel):
    """Model for auth token response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class TokenPayload(BaseModel):
    """Model for JWT token payload."""
    user_id: str
    exp: int  # expiration timestamp


# ==================== ERROR RESPONSE ====================

class ErrorResponse(BaseModel):
    """Standard error response."""
    detail: str
    error_code: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ==================== HEALTH CHECK ====================

class HealthCheckResponse(BaseModel):
    """Health check response."""
    status: str
    database: bool
    redis: bool
    timestamp: datetime = Field(default_factory=datetime.utcnow)