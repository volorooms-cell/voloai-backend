"""Booking-related database models."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:
    from app.models.listing import Listing
    from app.models.message import Conversation
    from app.models.payment import Payment, Refund
    from app.models.review import Review
    from app.models.user import User


class CalendarBlock(Base):
    """Calendar blocks for listing availability."""

    __tablename__ = "calendar_blocks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("listings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    block_type: Mapped[str] = mapped_column(
        String(20), default="manual"
    )  # manual, airbnb_sync, booking_sync, volo_booking
    external_booking_id: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    listing: Mapped["Listing"] = relationship("Listing", back_populates="calendar_blocks")


class Booking(Base):
    """Booking model."""

    __tablename__ = "bookings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    booking_number: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False, index=True
    )  # VOLO-XXXXXX
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("listings.id"), nullable=False, index=True
    )
    guest_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    host_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )

    # Source & Commission
    source: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # AIRBNB, BOOKING_COM, VOLO_MARKETPLACE, DIRECT_LINK, DIRECT_WHATSAPP
    commission_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False
    )  # 0.00 for direct, 9.00 for marketplace (flat rate includes gateway fees)

    # Dates
    check_in: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    check_out: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Guests
    adults: Mapped[int] = mapped_column(Integer, default=1)
    children: Mapped[int] = mapped_column(Integer, default=0)
    infants: Mapped[int] = mapped_column(Integer, default=0)

    # Pricing (in paisa - smallest currency unit)
    nightly_rate: Mapped[int] = mapped_column(Integer, nullable=False)
    subtotal: Mapped[int] = mapped_column(Integer, nullable=False)  # nightly_rate * nights
    cleaning_fee: Mapped[int] = mapped_column(Integer, default=0)
    service_fee: Mapped[int] = mapped_column(Integer, default=0)  # guest service fee
    taxes: Mapped[int] = mapped_column(Integer, default=0)
    total_price: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="PKR")

    # Commission (flat 9% on total_price for VOLO bookings)
    commission_amount: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # 9% of total_price (includes gateway fees)
    host_payout_amount: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # total_price - commission_amount

    # Status
    status: Mapped[str] = mapped_column(
        String(20), default="pending", index=True
    )  # pending, confirmed, cancelled, completed, no_show, disputed
    payment_status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending, paid, refunded, partially_refunded, failed

    # Cancellation
    cancelled_by: Mapped[str | None] = mapped_column(String(10))  # guest, host, admin
    cancellation_reason: Mapped[str | None] = mapped_column(Text)
    refund_amount: Mapped[int] = mapped_column(Integer, default=0)

    # Guest special requests
    special_requests: Mapped[str | None] = mapped_column(Text)

    # Timestamps
    booked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    listing: Mapped["Listing"] = relationship("Listing", back_populates="bookings")
    guest: Mapped["User"] = relationship(
        "User", back_populates="bookings_as_guest", foreign_keys=[guest_id]
    )
    host: Mapped["User"] = relationship(
        "User", back_populates="bookings_as_host", foreign_keys=[host_id]
    )
    extensions: Mapped[list["BookingExtension"]] = relationship(
        "BookingExtension", back_populates="booking", cascade="all, delete-orphan"
    )
    payments: Mapped[list["Payment"]] = relationship("Payment", back_populates="booking")
    refunds: Mapped[list["Refund"]] = relationship("Refund", back_populates="booking")
    conversation: Mapped["Conversation | None"] = relationship(
        "Conversation", back_populates="booking", uselist=False
    )
    reviews: Mapped[list["Review"]] = relationship("Review", back_populates="booking")

    @property
    def nights(self) -> int:
        """Calculate number of nights."""
        return (self.check_out - self.check_in).days

    @property
    def total_guests(self) -> int:
        """Calculate total guests."""
        return self.adults + self.children


class BookingExtension(Base):
    """Booking extension requests."""

    __tablename__ = "booking_extensions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=False
    )
    original_check_out: Mapped[date] = mapped_column(Date, nullable=False)
    new_check_out: Mapped[date] = mapped_column(Date, nullable=False)
    additional_nights: Mapped[int] = mapped_column(Integer, nullable=False)
    additional_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    commission_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending, approved, rejected
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    booking: Mapped["Booking"] = relationship("Booking", back_populates="extensions")
