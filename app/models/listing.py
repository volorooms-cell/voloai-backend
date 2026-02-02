"""Listing-related database models."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    ARRAY,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Time,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:
    from app.models.booking import Booking, CalendarBlock
    from app.models.message import Conversation
    from app.models.review import Review
    from app.models.user import User


class Listing(Base):
    """Property listing model."""

    __tablename__ = "listings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    host_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Basic Info
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    listing_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # entire_apartment, private_room, shared_room, guest_house, upper_portion
    property_type: Mapped[str | None] = mapped_column(String(50))  # house, apartment, villa, etc.

    # Location
    address_line1: Mapped[str | None] = mapped_column(String(255))
    address_line2: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    state_province: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    country: Mapped[str] = mapped_column(String(2), default="PK")
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 8))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(11, 8))

    # Capacity
    max_guests: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    bedrooms: Mapped[int] = mapped_column(Integer, default=0)
    beds: Mapped[int] = mapped_column(Integer, default=0)
    bathrooms: Mapped[Decimal] = mapped_column(Numeric(3, 1), default=Decimal("1"))

    # Pricing (in paisa - smallest currency unit)
    base_price_per_night: Mapped[int] = mapped_column(Integer, nullable=False)
    cleaning_fee: Mapped[int] = mapped_column(Integer, default=0)
    service_fee_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("5.00"))
    currency: Mapped[str] = mapped_column(String(3), default="PKR")

    # Policies
    cancellation_policy: Mapped[str] = mapped_column(
        String(30), default="flexible"
    )  # flexible, moderate, strict, super_strict
    check_in_time: Mapped[time] = mapped_column(Time, default=time(14, 0))
    check_out_time: Mapped[time] = mapped_column(Time, default=time(11, 0))
    min_nights: Mapped[int] = mapped_column(Integer, default=1)
    max_nights: Mapped[int] = mapped_column(Integer, default=365)
    instant_booking: Mapped[bool] = mapped_column(Boolean, default=False)

    # Status
    status: Mapped[str] = mapped_column(
        String(20), default="draft", index=True
    )  # draft, pending_approval, approved, rejected, suspended, deleted
    approval_notes: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Direct Booking
    direct_booking_slug: Mapped[str | None] = mapped_column(String(50), unique=True)
    whatsapp_ai_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    whatsapp_ai_greeting: Mapped[str | None] = mapped_column(Text)

    # External Channel Sync
    external_airbnb_id: Mapped[str | None] = mapped_column(String(100))
    external_booking_id: Mapped[str | None] = mapped_column(String(100))
    sync_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    host: Mapped["User"] = relationship(
        "User", back_populates="listings", foreign_keys=[host_id]
    )
    photos: Mapped[list["ListingPhoto"]] = relationship(
        "ListingPhoto", back_populates="listing", cascade="all, delete-orphan"
    )
    amenities: Mapped[list["ListingAmenity"]] = relationship(
        "ListingAmenity", back_populates="listing", cascade="all, delete-orphan"
    )
    house_rules: Mapped[list["HouseRule"]] = relationship(
        "HouseRule", back_populates="listing", cascade="all, delete-orphan"
    )
    pricing_rules: Mapped[list["PricingRule"]] = relationship(
        "PricingRule", back_populates="listing", cascade="all, delete-orphan"
    )
    calendar_blocks: Mapped[list["CalendarBlock"]] = relationship(
        "CalendarBlock", back_populates="listing", cascade="all, delete-orphan"
    )
    bookings: Mapped[list["Booking"]] = relationship("Booking", back_populates="listing")
    conversations: Mapped[list["Conversation"]] = relationship(
        "Conversation", back_populates="listing"
    )
    reviews: Mapped[list["Review"]] = relationship("Review", back_populates="listing")

    @property
    def cover_photo_url(self) -> str | None:
        """Get cover photo URL."""
        for photo in self.photos:
            if photo.is_cover:
                return photo.url
        return self.photos[0].url if self.photos else None


class ListingPhoto(Base):
    """Listing photo model."""

    __tablename__ = "listing_photos"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("listings.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    caption: Mapped[str | None] = mapped_column(String(255))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_cover: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    listing: Mapped["Listing"] = relationship("Listing", back_populates="photos")


class Amenity(Base):
    """Amenity reference table."""

    __tablename__ = "amenities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    category: Mapped[str | None] = mapped_column(
        String(50)
    )  # essentials, features, safety, location
    icon: Mapped[str | None] = mapped_column(String(50))

    # Relationships
    listing_amenities: Mapped[list["ListingAmenity"]] = relationship(
        "ListingAmenity", back_populates="amenity"
    )


class ListingAmenity(Base):
    """Many-to-many relationship between listings and amenities."""

    __tablename__ = "listing_amenities"

    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("listings.id", ondelete="CASCADE"),
        primary_key=True,
    )
    amenity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("amenities.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Relationships
    listing: Mapped["Listing"] = relationship("Listing", back_populates="amenities")
    amenity: Mapped["Amenity"] = relationship("Amenity", back_populates="listing_amenities")


class HouseRule(Base):
    """House rules for a listing."""

    __tablename__ = "house_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("listings.id", ondelete="CASCADE"), nullable=False
    )
    rule_type: Mapped[str | None] = mapped_column(
        String(50)
    )  # pets, smoking, events, quiet_hours, custom
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_allowed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    listing: Mapped["Listing"] = relationship("Listing", back_populates="house_rules")


class PricingRule(Base):
    """Dynamic pricing rules for a listing."""

    __tablename__ = "pricing_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("listings.id", ondelete="CASCADE"), nullable=False
    )
    rule_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # weekly_discount, monthly_discount, weekend_price, seasonal, last_minute
    discount_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    price_override: Mapped[int | None] = mapped_column(Integer)
    min_nights: Mapped[int | None] = mapped_column(Integer)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    days_of_week: Mapped[list[int] | None] = mapped_column(
        ARRAY(Integer)
    )  # 0=Sunday, 6=Saturday
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    listing: Mapped["Listing"] = relationship("Listing", back_populates="pricing_rules")
