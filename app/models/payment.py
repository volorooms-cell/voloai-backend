"""Payment-related database models."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import ARRAY, Date, DateTime, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.user import User


class Payment(Base):
    """Payment transaction model."""

    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    # Amount
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # in paisa
    currency: Mapped[str] = mapped_column(String(3), default="PKR")

    # Method
    payment_method: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # card, bank_transfer, jazzcash, easypaisa, apple_pay, google_pay

    # Gateway
    gateway: Mapped[str | None] = mapped_column(String(30))  # stripe, jazzcash, easypaisa
    gateway_transaction_id: Mapped[str | None] = mapped_column(String(100))
    gateway_response: Mapped[dict | None] = mapped_column(JSONB)
    gateway_fee_amount: Mapped[int] = mapped_column(
        Integer, default=0
    )  # Internal accounting only - not exposed in API

    # Status
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending, processing, completed, failed, refunded

    # Timestamps
    initiated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    booking: Mapped["Booking"] = relationship("Booking", back_populates="payments")
    user: Mapped["User"] = relationship("User")
    refunds: Mapped[list["Refund"]] = relationship("Refund", back_populates="payment")


class HostPayout(Base):
    """Host payout model."""

    __tablename__ = "host_payouts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    host_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    # Payout Details
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # in paisa
    currency: Mapped[str] = mapped_column(String(3), default="PKR")

    # Bank Details (encrypted)
    bank_name: Mapped[str | None] = mapped_column(String(100))
    account_number_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    account_holder_name: Mapped[str | None] = mapped_column(String(200))

    # Method
    payout_method: Mapped[str | None] = mapped_column(
        String(30)
    )  # bank_transfer, jazzcash, easypaisa

    # Status (state machine: pending → eligible → released, or → reversed)
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending, eligible, released, reversed

    # Gateway
    gateway_transaction_id: Mapped[str | None] = mapped_column(String(100))
    gateway_response: Mapped[dict | None] = mapped_column(JSONB)

    # Single booking reference (for per-booking payouts)
    booking_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id")
    )

    # Period
    payout_date: Mapped[date] = mapped_column(Date, nullable=False)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)

    # Bookings included
    booking_ids: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(UUID(as_uuid=True)))

    # Timestamps
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    host: Mapped["User"] = relationship("User", back_populates="payouts")
    deducted_refunds: Mapped[list["Refund"]] = relationship(
        "Refund", back_populates="deducted_from_payout"
    )


class Refund(Base):
    """Refund model."""

    __tablename__ = "refunds"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=False
    )
    payment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.id"), nullable=False
    )

    # Amount
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # in paisa
    reason: Mapped[str | None] = mapped_column(Text)

    # Status
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending, approved, processed, rejected

    # Deducted from host payout
    deducted_from_payout_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("host_payouts.id")
    )

    # Processing
    processed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    gateway_refund_id: Mapped[str | None] = mapped_column(String(100))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    booking: Mapped["Booking"] = relationship("Booking", back_populates="refunds")
    payment: Mapped["Payment"] = relationship("Payment", back_populates="refunds")
    deducted_from_payout: Mapped["HostPayout | None"] = relationship(
        "HostPayout", back_populates="deducted_refunds"
    )
