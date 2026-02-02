"""Financial reporting schemas (read-only)."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DailySettlementSummary(BaseModel):
    """Daily settlement summary for platform."""

    report_date: date
    total_payments_received: int
    total_refunds_issued: int
    total_payouts_released: int
    total_payouts_reversed: int
    net_position: int
    payment_count: int
    refund_count: int
    payout_count: int
    reversal_count: int
    currency: str = "PKR"


class MonthlySettlementSummary(BaseModel):
    """Monthly settlement summary for platform."""

    year: int
    month: int
    period_start: date
    period_end: date
    total_payments_received: int
    total_refunds_issued: int
    total_payouts_released: int
    total_payouts_reversed: int
    net_position: int
    total_commission_earned: int
    payment_count: int
    refund_count: int
    payout_count: int
    booking_count: int
    currency: str = "PKR"


class HostEarningsStatement(BaseModel):
    """Host earnings statement for a date range."""

    host_id: UUID
    host_email: str
    period_start: date
    period_end: date
    total_bookings: int
    total_nights: int
    gross_earnings: int
    commission_paid: int
    refunds_deducted: int
    net_earnings: int
    payouts_released: int
    payouts_pending: int
    currency: str = "PKR"


class HostEarningsLineItem(BaseModel):
    """Individual booking line item in host earnings."""

    model_config = ConfigDict(from_attributes=True)

    booking_id: UUID
    booking_number: str
    check_in: date
    check_out: date
    nights: int
    guest_total: int
    commission_rate: Decimal
    commission_amount: int
    host_payout_amount: int
    refund_amount: int = 0
    snapshot_at: datetime


class HostEarningsDetail(BaseModel):
    """Detailed host earnings with line items."""

    summary: HostEarningsStatement
    line_items: list[HostEarningsLineItem]


class PlatformRevenueReport(BaseModel):
    """Platform commission revenue report."""

    period_start: date
    period_end: date
    total_booking_value: int
    total_commission_earned: int
    average_commission_rate: Decimal
    booking_count: int
    by_source: dict[str, int]
    currency: str = "PKR"


class LedgerEntryExport(BaseModel):
    """Ledger entry for export."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    entry_type: str
    direction: str
    amount: int
    currency: str
    booking_id: UUID | None
    payment_id: UUID | None
    refund_id: UUID | None
    payout_id: UUID | None
    counterparty_type: str
    counterparty_id: UUID | None
    gateway: str | None
    gateway_transaction_id: str | None
    description: str | None
    effective_date: date
    created_at: datetime


class PayoutExport(BaseModel):
    """Payout record for export."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    host_id: UUID
    booking_id: UUID | None
    amount: int
    currency: str
    status: str
    payout_method: str | None
    payout_date: date
    processed_at: datetime | None
    created_at: datetime


class CommissionExport(BaseModel):
    """Commission record for export (from snapshots)."""

    booking_id: UUID
    booking_number: str
    guest_total: int
    commission_rate: Decimal
    commission_amount: int
    host_payout_amount: int
    source: str
    snapshot_at: datetime
    currency: str
