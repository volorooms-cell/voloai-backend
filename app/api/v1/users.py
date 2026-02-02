"""User endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_current_user, get_db
from app.core.encryption import get_encryption_service
from app.core.exceptions import NotFoundError, ValidationError
from app.models.user import User, UserIdentity
from app.schemas.user import (
    BecomeHostRequest,
    UserIdentityCreate,
    UserIdentityResponse,
    UserPublicResponse,
    UserResponse,
    UserUpdate,
)

router = APIRouter()


@router.get("/me", response_model=UserResponse)
async def get_my_profile(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Get current user's profile."""
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_my_profile(
    updates: UserUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Update current user's profile."""
    update_data = updates.model_dump(exclude_unset=True)

    # Check phone uniqueness if being updated
    if "phone" in update_data and update_data["phone"]:
        result = await db.execute(
            select(User).where(User.phone == update_data["phone"], User.id != current_user.id)
        )
        if result.scalar_one_or_none():
            raise ValidationError("Phone number already registered")

    # Apply updates
    for field, value in update_data.items():
        setattr(current_user, field, value)

    return current_user


@router.post("/me/identity", response_model=UserIdentityResponse, status_code=status.HTTP_201_CREATED)
async def create_identity_verification(
    identity_data: UserIdentityCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserIdentity:
    """Submit identity verification documents."""
    # Check if user already has pending or verified identity
    result = await db.execute(
        select(UserIdentity).where(
            UserIdentity.user_id == current_user.id,
            UserIdentity.verification_status.in_(["pending", "verified"]),
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        if existing.verification_status == "verified":
            raise ValidationError("Identity already verified")
        raise ValidationError("Identity verification already pending")

    # Encrypt document number
    encryption = get_encryption_service()
    encrypted_doc_number = encryption.encrypt(identity_data.document_number)

    # Create identity record
    identity = UserIdentity(
        user_id=current_user.id,
        document_type=identity_data.document_type,
        document_number_encrypted=encrypted_doc_number,
        document_front_url=identity_data.document_front_url,
        document_back_url=identity_data.document_back_url,
        face_scan_url=identity_data.face_scan_url,
        verification_status="pending",
    )
    db.add(identity)
    await db.flush()

    return identity


@router.get("/me/identity", response_model=UserIdentityResponse | None)
async def get_my_identity(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserIdentity | None:
    """Get current user's identity verification status."""
    result = await db.execute(
        select(UserIdentity)
        .where(UserIdentity.user_id == current_user.id)
        .order_by(UserIdentity.created_at.desc())
    )
    return result.scalar_one_or_none()


@router.post("/me/become-host", response_model=UserResponse)
async def become_host(
    request: BecomeHostRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Convert guest account to host account."""
    if current_user.role == "host":
        raise ValidationError("You are already a host")

    if current_user.role == "admin":
        raise ValidationError("Admin accounts cannot be converted to host")

    # Require identity verification
    if not current_user.is_verified:
        raise ValidationError("Identity verification required before becoming a host")

    # Update role
    current_user.role = "host"

    # TODO: Store encrypted bank details in a separate host_bank_details table
    # For now, we'll skip this as it requires additional model

    return current_user


@router.get("/{user_id}", response_model=UserPublicResponse)
async def get_user_profile(
    user_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Get public profile of a user."""
    result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))  # noqa: E712
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundError("User", str(user_id))
    return user
