"""Booking-related Pydantic schemas."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BookingBase(BaseModel):
    """Base booking schema."""

    listing_id: UUID
    check_in: date
    check_out: date
    adults: int = Field(default=1, ge=1, le=20)
    children: int = Field(default=0, ge=0, le=10)
    infants: int = Field(default=0, ge=0, le=5)
    special_requests: str | None = Field(None, max_length=1000)

    @field_validator("check_out")
    @classmethod
    def validate_checkout(cls, v: date, info) -> date:
        check_in = info.data.get("check_in")
        if check_in and v <= check_in:
            raise ValueError("check_out must be after check_in")
        return v


class BookingCreate(BookingBase):
    """Schema for creating a booking."""

    source: str = Field(
        default="VOLO_MARKETPLACE",
        pattern="^(VOLO_MARKETPLACE|DIRECT_LINK|DIRECT_WHATSAPP)$",
    )


class BookingUpdate(BaseModel):
    """Schema for updating a booking."""

    special_requests: str | None = Field(None, max_length=1000)


class BookingPriceBreakdown(BaseModel):
    """Schema for booking price breakdown."""

    nightly_rate: int
    nights: int
    subtotal: int
    cleaning_fee: int
    service_fee: int
    taxes: int
    total_price: int
    currency: str
    commission_rate: Decimal
    commission_amount: int
    host_payout_amount: int


class BookingResponse(BaseModel):
    """Schema for booking response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    booking_number: str
    listing_id: UUID
    guest_id: UUID
    host_id: UUID

    # Source & Commission
    source: str
    commission_rate: Decimal

    # Dates
    check_in: date
    check_out: date
    nights: int

    # Guests
    adults: int
    children: int
    infants: int

    # Pricing
    nightly_rate: int
    subtotal: int
    cleaning_fee: int
    service_fee: int
    taxes: int
    total_price: int
    currency: str

    # Commission
    commission_amount: int
    host_payout_amount: int

    # Status
    status: str
    payment_status: str

    # Cancellation
    cancelled_by: str | None
    cancellation_reason: str | None
    refund_amount: int

    # Special requests
    special_requests: str | None

    # Timestamps
    booked_at: datetime
    confirmed_at: datetime | None
    cancelled_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class BookingDetailResponse(BookingResponse):
    """Schema for detailed booking response with related data."""

    # These would be populated with related data
    listing_title: str | None = None
    listing_photo_url: str | None = None
    guest_name: str | None = None
    guest_photo_url: str | None = None
    host_name: str | None = None
    host_photo_url: str | None = None


class BookingListResponse(BaseModel):
    """Schema for paginated booking list."""

    bookings: list[BookingResponse]
    total: int
    page: int
    page_size: int


class BookingConfirmRequest(BaseModel):
    """Schema for host confirming a booking."""

    # Host can add a message when confirming
    message: str | None = Field(None, max_length=500)


class BookingCancelRequest(BaseModel):
    """Schema for canceling a booking."""

    reason: str = Field(..., min_length=10, max_length=1000)


class BookingExtensionCreate(BaseModel):
    """Schema for requesting a booking extension."""

    new_check_out: date

    @field_validator("new_check_out")
    @classmethod
    def validate_new_checkout(cls, v: date) -> date:
        from datetime import date as date_type

        if v <= date_type.today():
            raise ValueError("new_check_out must be in the future")
        return v


class BookingExtensionResponse(BaseModel):
    """Schema for booking extension response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    booking_id: UUID
    original_check_out: date
    new_check_out: date
    additional_nights: int
    additional_amount: int
    commission_amount: int
    status: str
    requested_at: datetime
    processed_at: datetime | None


class BookingCalculateRequest(BaseModel):
    """Schema for calculating booking price without creating."""

    listing_id: UUID
    check_in: date
    check_out: date
    guests: int = Field(default=1, ge=1, le=20)
    source: str = Field(
        default="VOLO_MARKETPLACE",
        pattern="^(VOLO_MARKETPLACE|DIRECT_LINK|DIRECT_WHATSAPP)$",
    )

    @field_validator("check_out")
    @classmethod
    def validate_checkout(cls, v: date, info) -> date:
        check_in = info.data.get("check_in")
        if check_in and v <= check_in:
            raise ValueError("check_out must be after check_in")
        return v


class BookingCalculateResponse(BaseModel):
    """Schema for booking price calculation response."""

    available: bool
    price_breakdown: BookingPriceBreakdown | None = None
    unavailable_reason: str | None = None
