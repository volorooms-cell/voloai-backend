"""Admin panel endpoints."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_db
from app.core.exceptions import NotFoundError, ValidationError
from app.models.admin import AuditLog, Dispute
from app.models.booking import Booking
from app.models.listing import Listing
from app.models.payment import Refund
from app.models.review import Review
from app.models.user import User, UserIdentity
from app.schemas.listing import ListingResponse
from app.schemas.payment import RefundCreate, RefundResponse
from app.schemas.review import ReviewModerationRequest, ReviewResponse
from app.schemas.user import UserResponse

router = APIRouter()


# ============ LISTING APPROVALS ============


@router.get("/listings/pending", response_model=list[ListingResponse])
async def get_pending_listings(
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Listing]:
    """Get listings pending approval."""
    result = await db.execute(
        select(Listing)
        .where(Listing.status == "pending_approval")
        .order_by(Listing.created_at.asc())
    )
    return list(result.scalars().all())


@router.post("/listings/{listing_id}/approve", response_model=ListingResponse)
async def approve_listing(
    listing_id: UUID,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    notes: str | None = None,
) -> Listing:
    """Approve a listing."""
    result = await db.execute(select(Listing).where(Listing.id == listing_id))
    listing = result.scalar_one_or_none()
    if not listing:
        raise NotFoundError("Listing", str(listing_id))

    if listing.status != "pending_approval":
        raise ValidationError("Listing is not pending approval")

    listing.status = "approved"
    listing.approved_by = admin.id
    listing.approved_at = datetime.now(UTC)
    listing.approval_notes = notes

    # Log action
    audit = AuditLog(
        user_id=admin.id,
        action="approve_listing",
        resource_type="listing",
        resource_id=listing_id,
        new_values={"status": "approved", "notes": notes},
    )
    db.add(audit)

    return listing


@router.post("/listings/{listing_id}/reject", response_model=ListingResponse)
async def reject_listing(
    listing_id: UUID,
    reason: str,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Listing:
    """Reject a listing."""
    result = await db.execute(select(Listing).where(Listing.id == listing_id))
    listing = result.scalar_one_or_none()
    if not listing:
        raise NotFoundError("Listing", str(listing_id))

    if listing.status != "pending_approval":
        raise ValidationError("Listing is not pending approval")

    listing.status = "rejected"
    listing.approval_notes = reason

    # Log action
    audit = AuditLog(
        user_id=admin.id,
        action="reject_listing",
        resource_type="listing",
        resource_id=listing_id,
        new_values={"status": "rejected", "reason": reason},
    )
    db.add(audit)

    return listing


# ============ USER MANAGEMENT ============


@router.get("/users", response_model=list[UserResponse])
async def get_users(
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    role: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> list[User]:
    """Get all users."""
    query = select(User)
    if role:
        query = query.where(User.role == role)

    offset = (page - 1) * page_size
    query = query.order_by(User.created_at.desc()).offset(offset).limit(page_size)

    result = await db.execute(query)
    return list(result.scalars().all())


@router.post("/users/{user_id}/suspend")
async def suspend_user(
    user_id: UUID,
    reason: str,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Suspend a user account."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundError("User", str(user_id))

    if user.role == "admin":
        raise ValidationError("Cannot suspend admin accounts")

    user.is_active = False

    # Log action
    audit = AuditLog(
        user_id=admin.id,
        action="suspend_user",
        resource_type="user",
        resource_id=user_id,
        new_values={"is_active": False, "reason": reason},
    )
    db.add(audit)

    return {"message": "User suspended", "user_id": str(user_id)}


@router.post("/users/{user_id}/activate")
async def activate_user(
    user_id: UUID,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Reactivate a suspended user."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundError("User", str(user_id))

    user.is_active = True

    # Log action
    audit = AuditLog(
        user_id=admin.id,
        action="activate_user",
        resource_type="user",
        resource_id=user_id,
        new_values={"is_active": True},
    )
    db.add(audit)

    return {"message": "User activated", "user_id": str(user_id)}


# ============ IDENTITY VERIFICATION ============


@router.get("/identity/pending")
async def get_pending_verifications(
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict]:
    """Get pending identity verifications."""
    result = await db.execute(
        select(UserIdentity)
        .where(UserIdentity.verification_status == "pending")
        .order_by(UserIdentity.created_at.asc())
    )
    identities = result.scalars().all()

    return [
        {
            "id": str(i.id),
            "user_id": str(i.user_id),
            "document_type": i.document_type,
            "document_front_url": i.document_front_url,
            "document_back_url": i.document_back_url,
            "face_scan_url": i.face_scan_url,
            "created_at": i.created_at.isoformat(),
        }
        for i in identities
    ]


@router.post("/identity/{identity_id}/verify")
async def verify_identity(
    identity_id: UUID,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Verify user identity."""
    result = await db.execute(select(UserIdentity).where(UserIdentity.id == identity_id))
    identity = result.scalar_one_or_none()
    if not identity:
        raise NotFoundError("Identity", str(identity_id))

    identity.verification_status = "verified"
    identity.verified_at = datetime.now(UTC)

    # Update user
    user_result = await db.execute(select(User).where(User.id == identity.user_id))
    user = user_result.scalar_one()
    user.is_verified = True

    return {"message": "Identity verified", "user_id": str(identity.user_id)}


@router.post("/identity/{identity_id}/reject")
async def reject_identity(
    identity_id: UUID,
    reason: str,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Reject identity verification."""
    result = await db.execute(select(UserIdentity).where(UserIdentity.id == identity_id))
    identity = result.scalar_one_or_none()
    if not identity:
        raise NotFoundError("Identity", str(identity_id))

    identity.verification_status = "rejected"
    identity.rejection_reason = reason

    return {"message": "Identity rejected", "identity_id": str(identity_id)}


# ============ DISPUTES ============


@router.get("/disputes")
async def get_disputes(
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: str | None = Query(default=None, alias="status"),
) -> list[dict]:
    """Get all disputes."""
    query = select(Dispute)
    if status_filter:
        query = query.where(Dispute.status == status_filter)
    query = query.order_by(Dispute.created_at.desc())

    result = await db.execute(query)
    disputes = result.scalars().all()

    return [
        {
            "id": str(d.id),
            "booking_id": str(d.booking_id),
            "raised_by": str(d.raised_by),
            "against_id": str(d.against_id),
            "category": d.category,
            "description": d.description,
            "status": d.status,
            "resolution": d.resolution,
            "refund_granted": d.refund_granted,
            "created_at": d.created_at.isoformat(),
        }
        for d in disputes
    ]


@router.patch("/disputes/{dispute_id}")
async def resolve_dispute(
    dispute_id: UUID,
    resolution: str,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    refund_amount: int = 0,
) -> dict:
    """Resolve a dispute."""
    result = await db.execute(select(Dispute).where(Dispute.id == dispute_id))
    dispute = result.scalar_one_or_none()
    if not dispute:
        raise NotFoundError("Dispute", str(dispute_id))

    dispute.status = "resolved"
    dispute.resolution = resolution
    dispute.refund_granted = refund_amount
    dispute.assigned_to = admin.id
    dispute.resolved_at = datetime.now(UTC)

    # Log action
    audit = AuditLog(
        user_id=admin.id,
        action="resolve_dispute",
        resource_type="dispute",
        resource_id=dispute_id,
        new_values={"resolution": resolution, "refund": refund_amount},
    )
    db.add(audit)

    return {"message": "Dispute resolved", "dispute_id": str(dispute_id)}


# ============ REFUNDS ============


@router.post("/refunds", response_model=RefundResponse)
async def create_refund(
    refund_data: RefundCreate,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Refund:
    """Process a refund."""
    # Get booking
    result = await db.execute(select(Booking).where(Booking.id == refund_data.booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise NotFoundError("Booking", str(refund_data.booking_id))

    if refund_data.amount > booking.total_price:
        raise ValidationError("Refund amount exceeds booking total")

    # Get payment
    from app.models.payment import Payment

    payment_result = await db.execute(
        select(Payment).where(
            Payment.booking_id == booking.id,
            Payment.status == "completed",
        )
    )
    payment = payment_result.scalar_one_or_none()
    if not payment:
        raise ValidationError("No completed payment found for this booking")

    refund = Refund(
        booking_id=booking.id,
        payment_id=payment.id,
        amount=refund_data.amount,
        reason=refund_data.reason,
        status="approved",
        processed_by=admin.id,
        processed_at=datetime.now(UTC),
    )
    db.add(refund)

    # Update booking
    booking.refund_amount = refund_data.amount
    booking.payment_status = "refunded" if refund_data.amount == booking.total_price else "partially_refunded"

    # Log action
    audit = AuditLog(
        user_id=admin.id,
        action="process_refund",
        resource_type="refund",
        resource_id=booking.id,
        new_values={"amount": refund_data.amount, "reason": refund_data.reason},
    )
    db.add(audit)

    await db.flush()
    return refund


# ============ REVIEW MODERATION ============


@router.get("/reviews/flagged", response_model=list[ReviewResponse])
async def get_flagged_reviews(
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Review]:
    """Get reviews that need moderation."""
    # In production, you'd have a flagging system
    # For now, return reviews with low ratings that might need review
    result = await db.execute(
        select(Review)
        .where(Review.overall_rating <= 2, Review.status == "published")
        .order_by(Review.created_at.desc())
        .limit(50)
    )
    return list(result.scalars().all())


@router.patch("/reviews/{review_id}")
async def moderate_review(
    review_id: UUID,
    moderation: ReviewModerationRequest,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Moderate a review."""
    result = await db.execute(select(Review).where(Review.id == review_id))
    review = result.scalar_one_or_none()
    if not review:
        raise NotFoundError("Review", str(review_id))

    review.status = moderation.status
    review.moderation_notes = moderation.moderation_notes
    review.moderated_by = admin.id

    # Log action
    audit = AuditLog(
        user_id=admin.id,
        action="moderate_review",
        resource_type="review",
        resource_id=review_id,
        new_values={"status": moderation.status, "notes": moderation.moderation_notes},
    )
    db.add(audit)

    return {"message": "Review moderated", "review_id": str(review_id), "status": moderation.status}


# ============ AUDIT LOGS ============


@router.get("/audit-logs")
async def get_audit_logs(
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> dict:
    """Get audit logs."""
    query = select(AuditLog).order_by(AuditLog.created_at.desc())

    # Count
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    # Pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    logs = result.scalars().all()

    return {
        "logs": [
            {
                "id": str(log.id),
                "user_id": str(log.user_id) if log.user_id else None,
                "action": log.action,
                "resource_type": log.resource_type,
                "resource_id": str(log.resource_id) if log.resource_id else None,
                "old_values": log.old_values,
                "new_values": log.new_values,
                "ip_address": str(log.ip_address) if log.ip_address else None,
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
