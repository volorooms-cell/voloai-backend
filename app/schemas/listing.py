"""Listing-related Pydantic schemas."""

from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ListingBase(BaseModel):
    """Base listing schema."""

    title: str = Field(..., min_length=5, max_length=100)
    description: str | None = Field(None, max_length=5000)
    listing_type: str = Field(
        ..., pattern="^(entire_apartment|private_room|shared_room|guest_house|upper_portion)$"
    )
    property_type: str | None = Field(None, max_length=50)

    # Location
    address_line1: str | None = Field(None, max_length=255)
    address_line2: str | None = Field(None, max_length=255)
    city: str = Field(..., max_length=100)
    state_province: str | None = Field(None, max_length=100)
    postal_code: str | None = Field(None, max_length=20)
    country: str = Field(default="PK", max_length=2)
    latitude: Decimal | None = None
    longitude: Decimal | None = None

    # Capacity
    max_guests: int = Field(default=1, ge=1, le=20)
    bedrooms: int = Field(default=0, ge=0, le=50)
    beds: int = Field(default=0, ge=0, le=50)
    bathrooms: Decimal = Field(default=Decimal("1"), ge=0, le=50)

    # Pricing (in whole PKR - will be converted to paisa in service)
    base_price_per_night: int = Field(..., ge=100, le=10000000)  # Min 100 PKR
    cleaning_fee: int = Field(default=0, ge=0, le=1000000)
    currency: str = Field(default="PKR", pattern="^(PKR|USD)$")

    # Policies
    cancellation_policy: str = Field(
        default="flexible", pattern="^(flexible|moderate|strict|super_strict)$"
    )
    check_in_time: time = Field(default=time(14, 0))
    check_out_time: time = Field(default=time(11, 0))
    min_nights: int = Field(default=1, ge=1, le=365)
    max_nights: int = Field(default=365, ge=1, le=365)
    instant_booking: bool = Field(default=False)


class ListingCreate(ListingBase):
    """Schema for creating a listing."""

    # Amenity IDs
    amenity_ids: list[UUID] = Field(default_factory=list)


class ListingUpdate(BaseModel):
    """Schema for updating a listing."""

    title: str | None = Field(None, min_length=5, max_length=100)
    description: str | None = Field(None, max_length=5000)
    listing_type: str | None = Field(
        None, pattern="^(entire_apartment|private_room|shared_room|guest_house|upper_portion)$"
    )
    property_type: str | None = Field(None, max_length=50)

    # Location
    address_line1: str | None = Field(None, max_length=255)
    address_line2: str | None = Field(None, max_length=255)
    city: str | None = Field(None, max_length=100)
    state_province: str | None = Field(None, max_length=100)
    postal_code: str | None = Field(None, max_length=20)
    latitude: Decimal | None = None
    longitude: Decimal | None = None

    # Capacity
    max_guests: int | None = Field(None, ge=1, le=20)
    bedrooms: int | None = Field(None, ge=0, le=50)
    beds: int | None = Field(None, ge=0, le=50)
    bathrooms: Decimal | None = Field(None, ge=0, le=50)

    # Pricing
    base_price_per_night: int | None = Field(None, ge=100, le=10000000)
    cleaning_fee: int | None = Field(None, ge=0, le=1000000)

    # Policies
    cancellation_policy: str | None = Field(
        None, pattern="^(flexible|moderate|strict|super_strict)$"
    )
    check_in_time: time | None = None
    check_out_time: time | None = None
    min_nights: int | None = Field(None, ge=1, le=365)
    max_nights: int | None = Field(None, ge=1, le=365)
    instant_booking: bool | None = None

    # Status
    status: str | None = Field(None, pattern="^(draft|pending_approval|approved|paused)$")

    # Direct booking
    whatsapp_ai_enabled: bool | None = None
    whatsapp_ai_greeting: str | None = Field(None, max_length=500)


class ListingPhotoCreate(BaseModel):
    """Schema for adding a listing photo."""

    url: str
    caption: str | None = Field(None, max_length=255)
    is_cover: bool = False


class ListingPhotoResponse(BaseModel):
    """Schema for listing photo response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    url: str
    caption: str | None
    sort_order: int
    is_cover: bool


class AmenityResponse(BaseModel):
    """Schema for amenity response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    category: str | None
    icon: str | None


class HouseRuleCreate(BaseModel):
    """Schema for creating a house rule."""

    rule_type: str | None = Field(None, pattern="^(pets|smoking|events|quiet_hours|custom)$")
    description: str = Field(..., max_length=500)
    is_allowed: bool = False


class HouseRuleResponse(BaseModel):
    """Schema for house rule response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    rule_type: str | None
    description: str
    is_allowed: bool


class PricingRuleCreate(BaseModel):
    """Schema for creating a pricing rule."""

    rule_type: str = Field(
        ..., pattern="^(weekly_discount|monthly_discount|weekend_price|seasonal|last_minute)$"
    )
    discount_percent: Decimal | None = Field(None, ge=0, le=100)
    price_override: int | None = Field(None, ge=0)
    min_nights: int | None = Field(None, ge=1)
    start_date: date | None = None
    end_date: date | None = None
    days_of_week: list[int] | None = None  # 0=Sunday, 6=Saturday

    @field_validator("days_of_week")
    @classmethod
    def validate_days(cls, v: list[int] | None) -> list[int] | None:
        if v is not None:
            for day in v:
                if day < 0 or day > 6:
                    raise ValueError("days_of_week must be 0-6")
        return v


class PricingRuleResponse(BaseModel):
    """Schema for pricing rule response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    rule_type: str
    discount_percent: Decimal | None
    price_override: int | None
    min_nights: int | None
    start_date: date | None
    end_date: date | None
    days_of_week: list[int] | None
    is_active: bool


class ListingResponse(BaseModel):
    """Schema for listing response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    host_id: UUID
    title: str
    description: str | None
    listing_type: str
    property_type: str | None

    # Location
    address_line1: str | None
    address_line2: str | None
    city: str
    state_province: str | None
    postal_code: str | None
    country: str
    latitude: Decimal | None
    longitude: Decimal | None

    # Capacity
    max_guests: int
    bedrooms: int
    beds: int
    bathrooms: Decimal

    # Pricing
    base_price_per_night: int
    cleaning_fee: int
    service_fee_percent: Decimal
    currency: str

    # Policies
    cancellation_policy: str
    check_in_time: time
    check_out_time: time
    min_nights: int
    max_nights: int
    instant_booking: bool

    # Status
    status: str
    approval_notes: str | None

    # Direct booking
    direct_booking_slug: str | None
    whatsapp_ai_enabled: bool

    # External sync
    sync_enabled: bool
    last_synced_at: datetime | None

    # Timestamps
    created_at: datetime
    updated_at: datetime

    # Related data (optional, populated based on include params)
    photos: list[ListingPhotoResponse] = []
    house_rules: list[HouseRuleResponse] = []
    pricing_rules: list[PricingRuleResponse] = []
    amenities: list[AmenityResponse] = []


class ListingSearchParams(BaseModel):
    """Schema for listing search parameters."""

    # Location
    city: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    radius_km: int = Field(default=10, ge=1, le=100)

    # Dates
    check_in: date | None = None
    check_out: date | None = None

    # Capacity
    guests: int = Field(default=1, ge=1, le=20)

    # Filters
    listing_type: list[str] | None = None
    min_price: int | None = Field(None, ge=0)
    max_price: int | None = Field(None, ge=0)
    instant_booking: bool | None = None
    amenity_ids: list[UUID] | None = None
    bedrooms_min: int | None = Field(None, ge=0)
    bathrooms_min: Decimal | None = Field(None, ge=0)

    # Pagination
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    # Sorting
    sort_by: str = Field(default="relevance", pattern="^(relevance|price_low|price_high|rating)$")


class ListingSearchResponse(BaseModel):
    """Schema for listing search results."""

    listings: list[ListingResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class CalendarBlockCreate(BaseModel):
    """Schema for creating a calendar block."""

    start_date: date
    end_date: date
    notes: str | None = Field(None, max_length=500)

    @field_validator("end_date")
    @classmethod
    def validate_end_date(cls, v: date, info) -> date:
        start = info.data.get("start_date")
        if start and v <= start:
            raise ValueError("end_date must be after start_date")
        return v


class CalendarBlockResponse(BaseModel):
    """Schema for calendar block response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    start_date: date
    end_date: date
    block_type: str
    notes: str | None


class CalendarAvailabilityResponse(BaseModel):
    """Schema for calendar availability response."""

    date: date
    available: bool
    price: int | None  # Dynamic price for the date
    min_nights: int


class DirectLinkResponse(BaseModel):
    """Schema for direct booking link response."""

    direct_booking_slug: str
    url: str
    qr_code_url: str
