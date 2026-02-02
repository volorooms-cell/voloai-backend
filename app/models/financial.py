"""Financial and accounting models.

Immutable records for settlement, reconciliation, and reporting.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.payment import HostPayout, Payment, Refund
    from app.models.user import User


class BookingFinancialSnapshot(Base):
    """Immutable financial snapshot captured at booking completion.

    This record MUST NOT be modified after creation.
    Used for settlement, reconciliation, and audit purposes.
    """

    __tablename__ = "booking_financial_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=False, unique=True
    )
    booking_number: Mapped[str] = mapped_column(String(20), nullable=False)

    # Guest payment
    guest_total: Mapped[int] = mapped_column(Integer, nullable=False)
    guest_subtotal: Mapped[int] = mapped_column(Integer, nullable=False)
    guest_cleaning_fee: Mapped[int] = mapped_column(Integer, nullable=False)
    guest_service_fee: Mapped[int] = mapped_column(Integer, nullable=False)
    guest_taxes: Mapped[int] = mapped_column(Integer, nullable=False)

    # VOLO commission
    commission_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    commission_amount: Mapped[int] = mapped_column(Integer, nullable=False)

    # Host payout
    host_payout_amount: Mapped[int] = mapped_column(Integer, nullable=False)

    # Currency
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    # Booking details at time of snapshot
    check_in: Mapped[date] = mapped_column(Date, nullable=False)
    check_out: Mapped[date] = mapped_column(Date, nullable=False)
    nights: Mapped[int] = mapped_column(Integer, nullable=False)
    nightly_rate: Mapped[int] = mapped_column(Integer, nullable=False)

    # Parties
    guest_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    host_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("listings.id"), nullable=False
    )

    # Source
    source: Mapped[str] = mapped_column(String(30), nullable=False)

    # Immutable timestamp
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    booking: Mapped["Booking"] = relationship("Booking")


class SettlementLedgerEntry(Base):
    """Ledger entry for financial reconciliation.

    Tracks all money movements: payments in, refunds out, payouts out.
    Each entry represents a single financial event.
    """

    __tablename__ = "settlement_ledger"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Entry type
    entry_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # payment_received, refund_issued, payout_released, payout_reversed

    # Direction: credit (money in) or debit (money out)
    direction: Mapped[str] = mapped_column(
        String(10), nullable=False
    )  # credit, debit

    # Amount (always positive, direction indicates flow)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="PKR")

    # References
    booking_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id")
    )
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.id")
    )
    refund_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("refunds.id")
    )
    payout_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("host_payouts.id")
    )

    # Counterparty
    counterparty_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # guest, host, gateway
    counterparty_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    # Gateway info
    gateway: Mapped[str | None] = mapped_column(String(30))
    gateway_transaction_id: Mapped[str | None] = mapped_column(String(100))

    # Description
    description: Mapped[str | None] = mapped_column(Text)

    # Timestamps
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    booking: Mapped["Booking | None"] = relationship("Booking")
    payment: Mapped["Payment | None"] = relationship("Payment")
    refund: Mapped["Refund | None"] = relationship("Refund")
    payout: Mapped["HostPayout | None"] = relationship("HostPayout")


class ReconciliationPeriod(Base):
    """Reconciliation period for settlement batches.

    Groups financial activity by period for reporting and settlement.
    """

    __tablename__ = "reconciliation_periods"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Period boundaries
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    period_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # daily, weekly, monthly

    # Aggregated totals
    total_payments_received: Mapped[int] = mapped_column(Integer, default=0)
    total_refunds_issued: Mapped[int] = mapped_column(Integer, default=0)
    total_payouts_released: Mapped[int] = mapped_column(Integer, default=0)
    total_commission_earned: Mapped[int] = mapped_column(Integer, default=0)

    # Counts
    payment_count: Mapped[int] = mapped_column(Integer, default=0)
    refund_count: Mapped[int] = mapped_column(Integer, default=0)
    payout_count: Mapped[int] = mapped_column(Integer, default=0)
    booking_count: Mapped[int] = mapped_column(Integer, default=0)

    # Net position
    net_position: Mapped[int] = mapped_column(Integer, default=0)  # payments - refunds - payouts

    # Status
    status: Mapped[str] = mapped_column(
        String(20), default="open"
    )  # open, closed, reconciled

    # Currency
    currency: Mapped[str] = mapped_column(String(3), default="PKR")

    # Metadata
    notes: Mapped[str | None] = mapped_column(Text)
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reconciled_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
