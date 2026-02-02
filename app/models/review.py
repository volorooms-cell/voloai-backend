"""Review database model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.listing import Listing
    from app.models.user import User


class Review(Base):
    """Review model for guest-to-host and host-to-guest reviews."""

    __tablename__ = "reviews"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=False
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("listings.id"), nullable=False, index=True
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    reviewee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )

    # Review Type
    review_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # guest_to_host, host_to_guest

    # Ratings (1-5)
    overall_rating: Mapped[int | None] = mapped_column(Integer)  # 1-5
    cleanliness_rating: Mapped[int | None] = mapped_column(Integer)
    accuracy_rating: Mapped[int | None] = mapped_column(Integer)
    communication_rating: Mapped[int | None] = mapped_column(Integer)
    location_rating: Mapped[int | None] = mapped_column(Integer)
    value_rating: Mapped[int | None] = mapped_column(Integer)
    checkin_rating: Mapped[int | None] = mapped_column(Integer)

    # Content
    public_review: Mapped[str | None] = mapped_column(Text)
    private_feedback: Mapped[str | None] = mapped_column(Text)  # Only visible to reviewee/VOLO

    # Moderation
    status: Mapped[str] = mapped_column(
        String(20), default="published"
    )  # pending, published, hidden, removed
    moderation_notes: Mapped[str | None] = mapped_column(Text)
    moderated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    booking: Mapped["Booking"] = relationship("Booking", back_populates="reviews")
    listing: Mapped["Listing"] = relationship("Listing", back_populates="reviews")
    reviewer: Mapped["User"] = relationship(
        "User", back_populates="reviews_given", foreign_keys=[reviewer_id]
    )
    reviewee: Mapped["User"] = relationship(
        "User", back_populates="reviews_received", foreign_keys=[reviewee_id]
    )
