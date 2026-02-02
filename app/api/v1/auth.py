"""Authentication endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.exceptions import AuthenticationError, ValidationError
from app.core.security import (
    create_tokens,
    get_password_hash,
    verify_password,
    verify_token,
)
from app.models.user import User
from app.schemas.user import (
    PasswordResetConfirm,
    PasswordResetRequest,
    PhoneVerificationConfirm,
    PhoneVerificationRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
)

router = APIRouter()


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Register a new user account."""
    # Check if email already exists
    result = await db.execute(select(User).where(User.email == user_data.email))
    if result.scalar_one_or_none():
        raise ValidationError("Email already registered")

    # Check if phone already exists (if provided)
    if user_data.phone:
        result = await db.execute(select(User).where(User.phone == user_data.phone))
        if result.scalar_one_or_none():
            raise ValidationError("Phone number already registered")

    # Create user
    user = User(
        email=user_data.email,
        phone=user_data.phone,
        password_hash=get_password_hash(user_data.password),
        role=user_data.role,
        first_name=user_data.first_name,
        last_name=user_data.last_name,
    )
    db.add(user)
    await db.flush()

    # Create tokens
    tokens = create_tokens(str(user.id), user.email, user.role)
    return TokenResponse(**tokens)


@router.post("/login", response_model=TokenResponse)
async def login(
    credentials: UserLogin,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Login with email and password."""
    # Find user by email
    result = await db.execute(select(User).where(User.email == credentials.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(credentials.password, user.password_hash):
        raise AuthenticationError("Invalid email or password")

    if not user.is_active:
        raise AuthenticationError("Account is deactivated")

    # Update last login
    from datetime import UTC, datetime

    user.last_login_at = datetime.now(UTC)

    # Create tokens
    tokens = create_tokens(str(user.id), user.email, user.role)
    return TokenResponse(**tokens)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshTokenRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Refresh access token using refresh token."""
    try:
        payload = verify_token(request.refresh_token, token_type="refresh")
        user_id = payload.get("sub")
        if not user_id:
            raise AuthenticationError("Invalid token")
    except Exception as e:
        raise AuthenticationError(str(e))

    # Verify user still exists and is active
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise AuthenticationError("User not found or inactive")

    # Create new tokens
    tokens = create_tokens(str(user.id), user.email, user.role)
    return TokenResponse(**tokens)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Logout user (client should discard tokens)."""
    # In a production system, you might want to:
    # 1. Add the token to a blacklist
    # 2. Invalidate refresh tokens in database
    # For now, the client is responsible for discarding tokens
    pass


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(
    request: PasswordResetRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """Request password reset email."""
    # Find user by email
    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalar_one_or_none()

    # Always return success to prevent email enumeration
    # In production, send reset email if user exists
    if user:
        # TODO: Generate reset token and send email
        pass

    return {"message": "If the email exists, a password reset link has been sent"}


@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(
    request: PasswordResetConfirm,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """Reset password with token."""
    # TODO: Verify reset token and update password
    # For now, return placeholder
    raise ValidationError("Password reset not implemented yet")


@router.post("/verify-phone/request", status_code=status.HTTP_202_ACCEPTED)
async def request_phone_verification(
    request: PhoneVerificationRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """Request phone OTP verification."""
    # Check if phone is already used by another user
    result = await db.execute(
        select(User).where(User.phone == request.phone, User.id != current_user.id)
    )
    if result.scalar_one_or_none():
        raise ValidationError("Phone number already registered to another user")

    # TODO: Send OTP via SMS (Twilio)
    return {"message": "OTP sent to phone number"}


@router.post("/verify-phone/confirm", status_code=status.HTTP_200_OK)
async def confirm_phone_verification(
    request: PhoneVerificationConfirm,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """Confirm phone OTP verification."""
    # TODO: Verify OTP
    # For now, just update phone
    current_user.phone = request.phone
    current_user.is_phone_verified = True
    return {"message": "Phone number verified successfully"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Get current authenticated user profile."""
    return current_user
