"""Payment-related Pydantic schemas."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PaymentCreate(BaseModel):
    """Schema for initiating a payment."""

    booking_id: UUID
    payment_method: str = Field(
        ..., pattern="^(card|bank_transfer|jazzcash|easypaisa|apple_pay|google_pay)$"
    )
    # For card payments
    stripe_payment_method_id: str | None = None
    # For mobile wallets
    wallet_account_number: str | None = None


class PaymentResponse(BaseModel):
    """Schema for payment response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    booking_id: UUID
    user_id: UUID
    amount: int
    currency: str
    payment_method: str
    gateway: str | None
    gateway_transaction_id: str | None
    status: str
    initiated_at: datetime
    completed_at: datetime | None
    created_at: datetime


class PaymentStatusResponse(BaseModel):
    """Schema for payment status check."""

    payment_id: UUID
    status: str
    booking_status: str
    message: str | None = None


class PaymentIntentResponse(BaseModel):
    """Schema for Stripe payment intent response."""

    client_secret: str
    payment_id: UUID


class PayoutResponse(BaseModel):
    """Schema for host payout response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    host_id: UUID
    amount: int
    currency: str
    payout_method: str | None
    status: str
    payout_date: date
    period_start: date | None
    period_end: date | None
    processed_at: datetime | None
    created_at: datetime


class PayoutListResponse(BaseModel):
    """Schema for paginated payout list."""

    payouts: list[PayoutResponse]
    total: int
    total_amount: int  # Sum of all payouts in paisa
    page: int
    page_size: int


class PayoutSettingsUpdate(BaseModel):
    """Schema for updating payout settings."""

    bank_name: str | None = Field(None, max_length=100)
    account_number: str | None = Field(None, min_length=10, max_length=30)
    account_holder_name: str | None = Field(None, max_length=200)
    payout_method: str | None = Field(None, pattern="^(bank_transfer|jazzcash|easypaisa)$")


class PayoutSettingsResponse(BaseModel):
    """Schema for payout settings response."""

    bank_name: str | None
    account_number_masked: str | None  # Show only last 4 digits
    account_holder_name: str | None
    payout_method: str | None


class RefundCreate(BaseModel):
    """Schema for creating a refund (admin only)."""

    booking_id: UUID
    amount: int = Field(..., gt=0)
    reason: str = Field(..., min_length=10, max_length=1000)


class PaymentRefundRequest(BaseModel):
    """Schema for refunding a payment."""

    amount: int | None = Field(None, gt=0, description="Refund amount in paisa. If not provided, full refund.")
    reason: str = Field(..., min_length=10, max_length=1000)


class RefundResponse(BaseModel):
    """Schema for refund response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    booking_id: UUID
    payment_id: UUID
    amount: int
    reason: str | None
    status: str
    processed_by: UUID | None
    processed_at: datetime | None
    created_at: datetime


class EarningsSummary(BaseModel):
    """Schema for host earnings summary."""

    total_earnings: int  # in paisa
    pending_payouts: int
    completed_payouts: int
    total_bookings: int
    average_nightly_rate: int
    occupancy_rate: float  # percentage
    period_start: date
    period_end: date
    currency: str = "PKR"
