"""Review-related Pydantic schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReviewCreate(BaseModel):
    """Schema for creating a review."""

    booking_id: UUID
    overall_rating: int = Field(..., ge=1, le=5)
    cleanliness_rating: int | None = Field(None, ge=1, le=5)
    accuracy_rating: int | None = Field(None, ge=1, le=5)
    communication_rating: int | None = Field(None, ge=1, le=5)
    location_rating: int | None = Field(None, ge=1, le=5)
    value_rating: int | None = Field(None, ge=1, le=5)
    checkin_rating: int | None = Field(None, ge=1, le=5)
    public_review: str | None = Field(None, min_length=10, max_length=2000)
    private_feedback: str | None = Field(None, max_length=1000)


class ReviewResponse(BaseModel):
    """Schema for review response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    booking_id: UUID
    listing_id: UUID
    reviewer_id: UUID
    reviewee_id: UUID
    review_type: str
    overall_rating: int | None
    cleanliness_rating: int | None
    accuracy_rating: int | None
    communication_rating: int | None
    location_rating: int | None
    value_rating: int | None
    checkin_rating: int | None
    public_review: str | None
    status: str
    created_at: datetime
    updated_at: datetime

    # Reviewer info (for display)
    reviewer_name: str | None = None
    reviewer_photo_url: str | None = None


class ReviewListResponse(BaseModel):
    """Schema for paginated review list."""

    reviews: list[ReviewResponse]
    total: int
    average_rating: float
    rating_breakdown: dict[int, int]  # {1: count, 2: count, ...}
    page: int
    page_size: int


class ReviewSummary(BaseModel):
    """Schema for review summary statistics."""

    total_reviews: int
    average_overall: float
    average_cleanliness: float | None
    average_accuracy: float | None
    average_communication: float | None
    average_location: float | None
    average_value: float | None
    average_checkin: float | None
    rating_breakdown: dict[int, int]


class ReviewModerationRequest(BaseModel):
    """Schema for admin review moderation."""

    status: str = Field(..., pattern="^(published|hidden|removed)$")
    moderation_notes: str | None = Field(None, max_length=500)
