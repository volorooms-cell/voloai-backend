"""Review endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db
from app.core.exceptions import NotFoundError, ValidationError
from app.models.booking import Booking
from app.models.review import Review
from app.models.user import User
from app.schemas.review import (
    ReviewCreate,
    ReviewListResponse,
    ReviewResponse,
    ReviewSummary,
)

router = APIRouter()


@router.post("/", response_model=ReviewResponse, status_code=201)
async def create_review(
    review_data: ReviewCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Review:
    """Create a review for a completed booking."""
    # Get booking
    result = await db.execute(select(Booking).where(Booking.id == review_data.booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise NotFoundError("Booking", str(review_data.booking_id))

    # Verify booking is completed
    if booking.status != "completed":
        raise ValidationError("Can only review completed bookings")

    # Determine review type and reviewee
    if current_user.id == booking.guest_id:
        review_type = "guest_to_host"
        reviewee_id = booking.host_id
    elif current_user.id == booking.host_id:
        review_type = "host_to_guest"
        reviewee_id = booking.guest_id
    else:
        raise ValidationError("You can only review bookings you participated in")

    # Check for existing review
    existing = await db.execute(
        select(Review).where(
            Review.booking_id == booking.id,
            Review.reviewer_id == current_user.id,
        )
    )
    if existing.scalar_one_or_none():
        raise ValidationError("You have already reviewed this booking")

    # Create review
    review = Review(
        booking_id=booking.id,
        listing_id=booking.listing_id,
        reviewer_id=current_user.id,
        reviewee_id=reviewee_id,
        review_type=review_type,
        overall_rating=review_data.overall_rating,
        cleanliness_rating=review_data.cleanliness_rating,
        accuracy_rating=review_data.accuracy_rating,
        communication_rating=review_data.communication_rating,
        location_rating=review_data.location_rating,
        value_rating=review_data.value_rating,
        checkin_rating=review_data.checkin_rating,
        public_review=review_data.public_review,
        private_feedback=review_data.private_feedback,
        status="published",
    )
    db.add(review)
    await db.flush()
    return review


@router.get("/listings/{listing_id}", response_model=ReviewListResponse)
async def get_listing_reviews(
    listing_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ReviewListResponse:
    """Get reviews for a listing."""
    query = select(Review).where(
        Review.listing_id == listing_id,
        Review.review_type == "guest_to_host",
        Review.status == "published",
    )

    # Count and average
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    avg_result = await db.execute(
        select(func.avg(Review.overall_rating)).where(
            Review.listing_id == listing_id,
            Review.review_type == "guest_to_host",
            Review.status == "published",
        )
    )
    avg_rating = float(avg_result.scalar() or 0)

    # Rating breakdown
    breakdown = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    breakdown_result = await db.execute(
        select(Review.overall_rating, func.count())
        .where(
            Review.listing_id == listing_id,
            Review.review_type == "guest_to_host",
            Review.status == "published",
        )
        .group_by(Review.overall_rating)
    )
    for rating, count in breakdown_result.all():
        if rating:
            breakdown[rating] = count

    # Pagination
    offset = (page - 1) * page_size
    query = query.order_by(Review.created_at.desc()).offset(offset).limit(page_size)

    result = await db.execute(query)
    reviews = list(result.scalars().all())

    return ReviewListResponse(
        reviews=[ReviewResponse.model_validate(r) for r in reviews],
        total=total,
        average_rating=avg_rating,
        rating_breakdown=breakdown,
        page=page,
        page_size=page_size,
    )


@router.get("/users/{user_id}", response_model=ReviewListResponse)
async def get_user_reviews(
    user_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ReviewListResponse:
    """Get reviews received by a user."""
    query = select(Review).where(
        Review.reviewee_id == user_id,
        Review.status == "published",
    )

    # Count and average
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    avg_result = await db.execute(
        select(func.avg(Review.overall_rating)).where(
            Review.reviewee_id == user_id,
            Review.status == "published",
        )
    )
    avg_rating = float(avg_result.scalar() or 0)

    # Rating breakdown
    breakdown = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    breakdown_result = await db.execute(
        select(Review.overall_rating, func.count())
        .where(Review.reviewee_id == user_id, Review.status == "published")
        .group_by(Review.overall_rating)
    )
    for rating, count in breakdown_result.all():
        if rating:
            breakdown[rating] = count

    # Pagination
    offset = (page - 1) * page_size
    query = query.order_by(Review.created_at.desc()).offset(offset).limit(page_size)

    result = await db.execute(query)
    reviews = list(result.scalars().all())

    return ReviewListResponse(
        reviews=[ReviewResponse.model_validate(r) for r in reviews],
        total=total,
        average_rating=avg_rating,
        rating_breakdown=breakdown,
        page=page,
        page_size=page_size,
    )


@router.get("/listings/{listing_id}/summary", response_model=ReviewSummary)
async def get_listing_review_summary(
    listing_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ReviewSummary:
    """Get review summary statistics for a listing."""
    base_filter = [
        Review.listing_id == listing_id,
        Review.review_type == "guest_to_host",
        Review.status == "published",
    ]

    # Get averages
    result = await db.execute(
        select(
            func.count(Review.id),
            func.avg(Review.overall_rating),
            func.avg(Review.cleanliness_rating),
            func.avg(Review.accuracy_rating),
            func.avg(Review.communication_rating),
            func.avg(Review.location_rating),
            func.avg(Review.value_rating),
            func.avg(Review.checkin_rating),
        ).where(*base_filter)
    )
    stats = result.one()

    # Rating breakdown
    breakdown = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    breakdown_result = await db.execute(
        select(Review.overall_rating, func.count())
        .where(*base_filter)
        .group_by(Review.overall_rating)
    )
    for rating, count in breakdown_result.all():
        if rating:
            breakdown[rating] = count

    return ReviewSummary(
        total_reviews=stats[0] or 0,
        average_overall=float(stats[1] or 0),
        average_cleanliness=float(stats[2]) if stats[2] else None,
        average_accuracy=float(stats[3]) if stats[3] else None,
        average_communication=float(stats[4]) if stats[4] else None,
        average_location=float(stats[5]) if stats[5] else None,
        average_value=float(stats[6]) if stats[6] else None,
        average_checkin=float(stats[7]) if stats[7] else None,
        rating_breakdown=breakdown,
    )
