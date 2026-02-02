"""Messaging-related Pydantic schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MessageCreate(BaseModel):
    """Schema for sending a message."""

    content: str = Field(..., min_length=1, max_length=5000)
    message_type: str = Field(default="text", pattern="^(text|image)$")
    image_url: str | None = None


class MessageResponse(BaseModel):
    """Schema for message response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    sender_id: UUID
    content: str
    message_type: str
    image_url: str | None
    is_read: bool
    read_at: datetime | None
    created_at: datetime


class ConversationResponse(BaseModel):
    """Schema for conversation response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    booking_id: UUID | None
    listing_id: UUID
    guest_id: UUID
    host_id: UUID
    last_message_at: datetime | None
    created_at: datetime

    # Computed fields for convenience
    unread_count: int = 0
    last_message: MessageResponse | None = None

    # Related data
    listing_title: str | None = None
    listing_photo_url: str | None = None
    other_user_name: str | None = None
    other_user_photo_url: str | None = None


class ConversationListResponse(BaseModel):
    """Schema for paginated conversation list."""

    conversations: list[ConversationResponse]
    total: int
    page: int
    page_size: int


class ConversationMessagesResponse(BaseModel):
    """Schema for conversation messages response."""

    conversation: ConversationResponse
    messages: list[MessageResponse]
    total: int
    page: int
    page_size: int


class MarkReadRequest(BaseModel):
    """Schema for marking messages as read."""

    message_ids: list[UUID] | None = None  # If None, mark all as read


class NotificationResponse(BaseModel):
    """Schema for notification response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    body: str
    notification_type: str
    action_url: str | None
    booking_id: UUID | None
    listing_id: UUID | None
    is_read: bool
    read_at: datetime | None
    created_at: datetime


class NotificationListResponse(BaseModel):
    """Schema for paginated notification list."""

    notifications: list[NotificationResponse]
    total: int
    unread_count: int
    page: int
    page_size: int


class PushTokenRegister(BaseModel):
    """Schema for registering push notification token."""

    token: str = Field(..., min_length=10, max_length=500)
    platform: str = Field(..., pattern="^(ios|android|web)$")
