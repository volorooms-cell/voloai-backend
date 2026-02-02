"""User-related Pydantic schemas."""

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserBase(BaseModel):
    """Base user schema."""

    email: EmailStr
    phone: str | None = None
    first_name: str | None = Field(None, max_length=100)
    last_name: str | None = Field(None, max_length=100)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        # Pakistan phone format: +92XXXXXXXXXX
        pattern = r"^\+92[0-9]{10}$"
        if not re.match(pattern, v):
            raise ValueError("Phone must be in format +92XXXXXXXXXX")
        return v


class UserCreate(UserBase):
    """Schema for user registration."""

    password: str = Field(..., min_length=8, max_length=128)
    role: str = Field(default="guest", pattern="^(guest|host)$")

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        return v


class UserLogin(BaseModel):
    """Schema for user login."""

    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    """Schema for updating user profile."""

    first_name: str | None = Field(None, max_length=100)
    last_name: str | None = Field(None, max_length=100)
    phone: str | None = None
    bio: str | None = Field(None, max_length=500)
    profile_photo_url: str | None = None
    preferred_language: str | None = Field(None, pattern="^(en|ur)$")
    preferred_currency: str | None = Field(None, pattern="^(PKR|USD)$")

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        pattern = r"^\+92[0-9]{10}$"
        if not re.match(pattern, v):
            raise ValueError("Phone must be in format +92XXXXXXXXXX")
        return v


class UserResponse(BaseModel):
    """Schema for user response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    phone: str | None
    first_name: str | None
    last_name: str | None
    profile_photo_url: str | None
    bio: str | None
    role: str
    is_verified: bool
    is_active: bool
    preferred_language: str
    preferred_currency: str
    loyalty_tier: str
    total_stays: int
    total_nights: int
    created_at: datetime


class UserPublicResponse(BaseModel):
    """Schema for public user profile (visible to others)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    first_name: str | None
    last_name: str | None
    profile_photo_url: str | None
    bio: str | None
    is_verified: bool
    loyalty_tier: str
    created_at: datetime


class TokenResponse(BaseModel):
    """Schema for authentication token response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    """Schema for token refresh request."""

    refresh_token: str


class PasswordResetRequest(BaseModel):
    """Schema for password reset request."""

    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Schema for password reset confirmation."""

    token: str
    new_password: str = Field(..., min_length=8, max_length=128)


class PhoneVerificationRequest(BaseModel):
    """Schema for phone verification request."""

    phone: str

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        pattern = r"^\+92[0-9]{10}$"
        if not re.match(pattern, v):
            raise ValueError("Phone must be in format +92XXXXXXXXXX")
        return v


class PhoneVerificationConfirm(BaseModel):
    """Schema for phone OTP verification."""

    phone: str
    otp: str = Field(..., min_length=6, max_length=6)


class UserIdentityCreate(BaseModel):
    """Schema for creating user identity verification."""

    document_type: str = Field(..., pattern="^(cnic|passport)$")
    document_number: str = Field(..., min_length=5, max_length=50)
    document_front_url: str
    document_back_url: str | None = None
    face_scan_url: str


class UserIdentityResponse(BaseModel):
    """Schema for user identity response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_type: str
    verification_status: str
    verified_at: datetime | None
    expires_at: datetime | None
    created_at: datetime


class BecomeHostRequest(BaseModel):
    """Schema for becoming a host."""

    # Host must provide bank details
    bank_name: str = Field(..., max_length=100)
    account_number: str = Field(..., min_length=10, max_length=30)
    account_holder_name: str = Field(..., max_length=200)
    payout_method: str = Field(default="bank_transfer", pattern="^(bank_transfer|jazzcash|easypaisa)$")
