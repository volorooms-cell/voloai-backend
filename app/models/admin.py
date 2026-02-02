"""Admin-related database models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ARRAY, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.user import User


class AuditLog(Base):
    """Audit log for tracking important actions."""

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )

    # Action details
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    # Changes
    old_values: Mapped[dict | None] = mapped_column(JSONB)
    new_values: Mapped[dict | None] = mapped_column(JSONB)

    # Request info
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    # Relationships
    user: Mapped["User | None"] = relationship("User")


class Dispute(Base):
    """Dispute resolution model."""

    __tablename__ = "disputes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=False
    )
    raised_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    against_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    # Details
    category: Mapped[str] = mapped_column(String(50), nullable=False)  # property_issue, host_issue, guest_issue, payment, chargeback, other
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_urls: Mapped[list[str] | None] = mapped_column(ARRAY(Text))

    # Status: opened → under_review → resolved → reversed
    status: Mapped[str] = mapped_column(
        String(20), default="opened"
    )

    # Resolution
    resolution: Mapped[str | None] = mapped_column(Text)
    resolution_type: Mapped[str | None] = mapped_column(String(30))  # refund, payout_reversal, no_action, chargeback_won, chargeback_lost
    refund_granted: Mapped[int] = mapped_column(default=0)  # in paisa
    payout_adjusted: Mapped[int] = mapped_column(default=0)  # in paisa

    # Assignment
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    booking: Mapped["Booking"] = relationship("Booking")
    raiser: Mapped["User"] = relationship("User", foreign_keys=[raised_by])
    against: Mapped["User"] = relationship("User", foreign_keys=[against_id])
    assignee: Mapped["User | None"] = relationship("User", foreign_keys=[assigned_to])
    resolver: Mapped["User | None"] = relationship("User", foreign_keys=[resolved_by])
