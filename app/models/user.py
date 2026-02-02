"""User-related database models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.listing import Listing
    from app.models.message import Conversation
    from app.models.payment import HostPayout
    from app.models.review import Review


class User(Base):
    """User account model."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, default="guest"
    )  # guest, host, cohost, admin

    # Profile
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    profile_photo_url: Mapped[str | None] = mapped_column(Text)
    bio: Mapped[str | None] = mapped_column(Text)

    # Status
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_phone_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    # Preferences
    preferred_language: Mapped[str] = mapped_column(String(10), default="en")
    preferred_currency: Mapped[str] = mapped_column(String(3), default="PKR")

    # Loyalty
    loyalty_tier: Mapped[str] = mapped_column(
        String(20), default="bronze"
    )  # bronze, silver, gold, platinum
    total_stays: Mapped[int] = mapped_column(default=0)
    total_nights: Mapped[int] = mapped_column(default=0)

    # Push notification token
    push_token: Mapped[str | None] = mapped_column(Text)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    identity: Mapped["UserIdentity | None"] = relationship(
        "UserIdentity", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    listings: Mapped[list["Listing"]] = relationship(
        "Listing", back_populates="host", foreign_keys="[Listing.host_id]"
    )
    bookings_as_guest: Mapped[list["Booking"]] = relationship(
        "Booking", back_populates="guest", foreign_keys="[Booking.guest_id]"
    )
    bookings_as_host: Mapped[list["Booking"]] = relationship(
        "Booking", back_populates="host", foreign_keys="[Booking.host_id]"
    )
    cohost_permissions_given: Mapped[list["CohostPermission"]] = relationship(
        "CohostPermission", back_populates="host", foreign_keys="[CohostPermission.host_id]"
    )
    cohost_permissions_received: Mapped[list["CohostPermission"]] = relationship(
        "CohostPermission", back_populates="cohost", foreign_keys="[CohostPermission.cohost_id]"
    )
    conversations_as_guest: Mapped[list["Conversation"]] = relationship(
        "Conversation", back_populates="guest", foreign_keys="[Conversation.guest_id]"
    )
    conversations_as_host: Mapped[list["Conversation"]] = relationship(
        "Conversation", back_populates="host", foreign_keys="[Conversation.host_id]"
    )
    reviews_given: Mapped[list["Review"]] = relationship(
        "Review", back_populates="reviewer", foreign_keys="[Review.reviewer_id]"
    )
    reviews_received: Mapped[list["Review"]] = relationship(
        "Review", back_populates="reviewee", foreign_keys="[Review.reviewee_id]"
    )
    payouts: Mapped[list["HostPayout"]] = relationship("HostPayout", back_populates="host")

    @property
    def full_name(self) -> str:
        """Get user's full name."""
        parts = [self.first_name, self.last_name]
        return " ".join(p for p in parts if p) or "Guest"


class UserIdentity(Base):
    """User identity verification documents."""

    __tablename__ = "user_identity"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Document type: cnic, passport
    document_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # Encrypted document number (AES-256-GCM)
    document_number_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    # Document images (S3 URLs, files encrypted at rest)
    document_front_url: Mapped[str] = mapped_column(Text, nullable=False)
    document_back_url: Mapped[str | None] = mapped_column(Text)
    face_scan_url: Mapped[str] = mapped_column(Text, nullable=False)

    # Verification status: pending, verified, rejected
    verification_status: Mapped[str] = mapped_column(String(20), default="pending")
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="identity")


class CohostPermission(Base):
    """Co-host permissions for listings."""

    __tablename__ = "cohost_permissions"
    __table_args__ = (
        UniqueConstraint("host_id", "cohost_id", "listing_id", name="unique_cohost_permission"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    host_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    cohost_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    listing_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("listings.id", ondelete="CASCADE")
    )  # NULL = all listings

    # Permissions
    can_manage_bookings: Mapped[bool] = mapped_column(Boolean, default=True)
    can_manage_calendar: Mapped[bool] = mapped_column(Boolean, default=True)
    can_manage_pricing: Mapped[bool] = mapped_column(Boolean, default=False)
    can_message_guests: Mapped[bool] = mapped_column(Boolean, default=True)
    can_view_payouts: Mapped[bool] = mapped_column(Boolean, default=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    host: Mapped["User"] = relationship(
        "User", back_populates="cohost_permissions_given", foreign_keys=[host_id]
    )
    cohost: Mapped["User"] = relationship(
        "User", back_populates="cohost_permissions_received", foreign_keys=[cohost_id]
    )
