"""Role-based access control and permissions."""

from enum import Enum
from functools import wraps
from typing import Any, Callable

from fastapi import Depends, HTTPException, status

from app.api.deps import get_current_user
from app.models.user import User


class UserRole(str, Enum):
    """User roles in the system."""

    GUEST = "guest"
    HOST = "host"
    COHOST = "cohost"
    OPS = "ops"  # Operations - can approve but not release
    ADMIN = "admin"


class Permission(str, Enum):
    """System permissions."""

    # User permissions
    VIEW_PROFILE = "view_profile"
    EDIT_PROFILE = "edit_profile"

    # Listing permissions
    CREATE_LISTING = "create_listing"
    EDIT_LISTING = "edit_listing"
    DELETE_LISTING = "delete_listing"
    VIEW_LISTING = "view_listing"
    APPROVE_LISTING = "approve_listing"

    # Booking permissions
    CREATE_BOOKING = "create_booking"
    CANCEL_BOOKING = "cancel_booking"
    CONFIRM_BOOKING = "confirm_booking"
    VIEW_BOOKING = "view_booking"

    # Payment permissions
    VIEW_PAYOUTS = "view_payouts"
    MANAGE_PAYOUTS = "manage_payouts"
    PROCESS_REFUNDS = "process_refunds"

    # Admin permissions
    VIEW_ALL_USERS = "view_all_users"
    MANAGE_USERS = "manage_users"
    VIEW_AUDIT_LOGS = "view_audit_logs"
    MANAGE_DISPUTES = "manage_disputes"
    MODERATE_REVIEWS = "moderate_reviews"

    # Financial operations (granular)
    PAYMENT_APPROVE = "payment_approve"
    REFUND_APPROVE = "refund_approve"
    PAYOUT_MARK_ELIGIBLE = "payout_mark_eligible"
    PAYOUT_RELEASE = "payout_release"
    PAYOUT_REVERSE = "payout_reverse"
    DISPUTE_RESOLVE = "dispute_resolve"
    FINANCIAL_EXPORT = "financial_export"


# Role to permissions mapping
ROLE_PERMISSIONS: dict[UserRole, set[Permission]] = {
    UserRole.GUEST: {
        Permission.VIEW_PROFILE,
        Permission.EDIT_PROFILE,
        Permission.VIEW_LISTING,
        Permission.CREATE_BOOKING,
        Permission.CANCEL_BOOKING,
        Permission.VIEW_BOOKING,
    },
    UserRole.HOST: {
        Permission.VIEW_PROFILE,
        Permission.EDIT_PROFILE,
        Permission.VIEW_LISTING,
        Permission.CREATE_LISTING,
        Permission.EDIT_LISTING,
        Permission.DELETE_LISTING,
        Permission.CREATE_BOOKING,
        Permission.CANCEL_BOOKING,
        Permission.CONFIRM_BOOKING,
        Permission.VIEW_BOOKING,
        Permission.VIEW_PAYOUTS,
    },
    UserRole.COHOST: {
        Permission.VIEW_PROFILE,
        Permission.VIEW_LISTING,
        Permission.EDIT_LISTING,
        Permission.CONFIRM_BOOKING,
        Permission.VIEW_BOOKING,
    },
    UserRole.OPS: {
        # Operations can view and approve, but not release or reverse
        Permission.VIEW_PROFILE,
        Permission.VIEW_LISTING,
        Permission.VIEW_BOOKING,
        Permission.VIEW_PAYOUTS,
        Permission.VIEW_ALL_USERS,
        Permission.VIEW_AUDIT_LOGS,
        Permission.MANAGE_DISPUTES,
        Permission.PAYMENT_APPROVE,
        Permission.REFUND_APPROVE,
        Permission.PAYOUT_MARK_ELIGIBLE,
        Permission.DISPUTE_RESOLVE,
    },
    UserRole.ADMIN: {
        # Admins have all permissions
        perm for perm in Permission
    },
}


def has_permission(role: UserRole, permission: Permission) -> bool:
    """Check if a role has a specific permission."""
    return permission in ROLE_PERMISSIONS.get(role, set())


def require_role(*allowed_roles: UserRole) -> Callable[..., Any]:
    """Dependency to require specific roles."""

    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        user_role = UserRole(current_user.role)
        if user_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role}' is not authorized for this action",
            )
        return current_user

    return role_checker


def require_permission(permission: Permission) -> Callable[..., Any]:
    """Dependency to require a specific permission."""

    async def permission_checker(current_user: User = Depends(get_current_user)) -> User:
        user_role = UserRole(current_user.role)
        if not has_permission(user_role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission.value}' is required for this action",
            )
        return current_user

    return permission_checker


# Convenience dependencies
require_admin = require_role(UserRole.ADMIN)
require_host = require_role(UserRole.HOST, UserRole.ADMIN)
require_host_or_cohost = require_role(UserRole.HOST, UserRole.COHOST, UserRole.ADMIN)
require_ops_or_admin = require_role(UserRole.OPS, UserRole.ADMIN)

# Financial operation dependencies
require_payment_approve = require_permission(Permission.PAYMENT_APPROVE)
require_refund_approve = require_permission(Permission.REFUND_APPROVE)
require_payout_eligible = require_permission(Permission.PAYOUT_MARK_ELIGIBLE)
require_payout_release = require_permission(Permission.PAYOUT_RELEASE)
require_payout_reverse = require_permission(Permission.PAYOUT_REVERSE)
require_dispute_resolve = require_permission(Permission.DISPUTE_RESOLVE)
require_financial_export = require_permission(Permission.FINANCIAL_EXPORT)
