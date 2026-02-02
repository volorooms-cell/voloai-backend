"""API dependencies for authentication and common operations."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, AuthorizationError, NotFoundError
from app.core.security import verify_token
from app.database import get_db
from app.models.user import CohostPermission, User

# Security scheme
security = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Get the current authenticated user from JWT token."""
    try:
        payload = verify_token(credentials.credentials, token_type="access")
        user_id = payload.get("sub")
        if not user_id:
            raise AuthenticationError("Invalid token payload")
    except Exception as e:
        raise AuthenticationError(str(e))

    # Fetch user from database
    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()

    if not user:
        raise AuthenticationError("User not found")
    if not user.is_active:
        raise AuthenticationError("User account is deactivated")

    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Get current user and verify they are active."""
    if not current_user.is_active:
        raise AuthorizationError("User account is deactivated")
    return current_user


async def get_current_verified_user(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    """Get current user and verify they have completed identity verification."""
    if not current_user.is_verified:
        raise AuthorizationError("Identity verification required")
    return current_user


async def get_current_host(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    """Get current user and verify they are a host."""
    if current_user.role not in ("host", "admin"):
        raise AuthorizationError("Host access required")
    return current_user


async def get_current_admin(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    """Get current user and verify they are an admin."""
    if current_user.role != "admin":
        raise AuthorizationError("Admin access required")
    return current_user


async def get_optional_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(HTTPBearer(auto_error=False))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User | None:
    """Optionally get the current user if authenticated."""
    if not credentials:
        return None

    try:
        payload = verify_token(credentials.credentials, token_type="access")
        user_id = payload.get("sub")
        if not user_id:
            return None

        result = await db.execute(select(User).where(User.id == UUID(user_id)))
        user = result.scalar_one_or_none()
        return user if user and user.is_active else None
    except Exception:
        return None


class ListingPermissionChecker:
    """Check if user has permission to manage a listing."""

    def __init__(self, require_owner: bool = False):
        self.require_owner = require_owner

    async def __call__(
        self,
        listing_id: UUID,
        current_user: Annotated[User, Depends(get_current_active_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> User:
        """Check listing permissions."""
        from app.models.listing import Listing

        # Admin always has access
        if current_user.role == "admin":
            return current_user

        # Get the listing
        result = await db.execute(select(Listing).where(Listing.id == listing_id))
        listing = result.scalar_one_or_none()

        if not listing:
            raise NotFoundError("Listing", str(listing_id))

        # Check if user is the owner
        if listing.host_id == current_user.id:
            return current_user

        # If owner is required, deny access
        if self.require_owner:
            raise AuthorizationError("Only the listing owner can perform this action")

        # Check for cohost permissions
        result = await db.execute(
            select(CohostPermission).where(
                CohostPermission.host_id == listing.host_id,
                CohostPermission.cohost_id == current_user.id,
                (CohostPermission.listing_id == listing_id) | (CohostPermission.listing_id.is_(None)),
            )
        )
        permission = result.scalar_one_or_none()

        if not permission:
            raise AuthorizationError("You don't have permission to access this listing")

        return current_user


class BookingPermissionChecker:
    """Check if user has permission to access a booking."""

    def __init__(self, allow_guest: bool = True, allow_host: bool = True):
        self.allow_guest = allow_guest
        self.allow_host = allow_host

    async def __call__(
        self,
        booking_id: UUID,
        current_user: Annotated[User, Depends(get_current_active_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> User:
        """Check booking permissions."""
        from app.models.booking import Booking

        # Admin always has access
        if current_user.role == "admin":
            return current_user

        # Get the booking
        result = await db.execute(select(Booking).where(Booking.id == booking_id))
        booking = result.scalar_one_or_none()

        if not booking:
            raise NotFoundError("Booking", str(booking_id))

        # Check if user is the guest
        if self.allow_guest and booking.guest_id == current_user.id:
            return current_user

        # Check if user is the host
        if self.allow_host and booking.host_id == current_user.id:
            return current_user

        # Check for cohost permissions
        result = await db.execute(
            select(CohostPermission).where(
                CohostPermission.host_id == booking.host_id,
                CohostPermission.cohost_id == current_user.id,
                CohostPermission.can_manage_bookings == True,  # noqa: E712
            )
        )
        permission = result.scalar_one_or_none()

        if permission:
            return current_user

        raise AuthorizationError("You don't have permission to access this booking")


# Convenience instances
require_listing_owner = ListingPermissionChecker(require_owner=True)
require_listing_access = ListingPermissionChecker(require_owner=False)
require_booking_access = BookingPermissionChecker(allow_guest=True, allow_host=True)
require_host_booking_access = BookingPermissionChecker(allow_guest=False, allow_host=True)
require_guest_booking_access = BookingPermissionChecker(allow_guest=True, allow_host=False)
