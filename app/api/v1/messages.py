"""Messaging endpoints."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_active_user, get_db
from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.models.listing import Listing
from app.models.message import Conversation, Message
from app.models.user import User
from app.schemas.message import (
    ConversationListResponse,
    ConversationMessagesResponse,
    ConversationResponse,
    MarkReadRequest,
    MessageCreate,
    MessageResponse,
)

router = APIRouter()


@router.get("/", response_model=ConversationListResponse)
async def get_conversations(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ConversationListResponse:
    """Get user's conversations."""
    query = (
        select(Conversation)
        .where(
            or_(
                Conversation.guest_id == current_user.id,
                Conversation.host_id == current_user.id,
            )
        )
        .options(selectinload(Conversation.messages))
    )

    # Count total
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    # Pagination
    offset = (page - 1) * page_size
    query = query.order_by(Conversation.last_message_at.desc().nullsfirst()).offset(offset).limit(page_size)

    result = await db.execute(query)
    conversations = list(result.scalars().all())

    # Build response with additional info
    response_conversations = []
    for conv in conversations:
        # Get unread count
        unread_count = sum(
            1 for m in conv.messages
            if not m.is_read and m.sender_id != current_user.id
        )

        # Get last message
        last_message = None
        if conv.messages:
            sorted_messages = sorted(conv.messages, key=lambda m: m.created_at, reverse=True)
            last_message = MessageResponse.model_validate(sorted_messages[0])

        response_conversations.append(
            ConversationResponse(
                id=conv.id,
                booking_id=conv.booking_id,
                listing_id=conv.listing_id,
                guest_id=conv.guest_id,
                host_id=conv.host_id,
                last_message_at=conv.last_message_at,
                created_at=conv.created_at,
                unread_count=unread_count,
                last_message=last_message,
            )
        )

    return ConversationListResponse(
        conversations=response_conversations,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{conversation_id}", response_model=ConversationMessagesResponse)
async def get_conversation_messages(
    conversation_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> ConversationMessagesResponse:
    """Get messages in a conversation."""
    # Get conversation
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise NotFoundError("Conversation", str(conversation_id))

    # Check permission
    if current_user.id not in (conversation.guest_id, conversation.host_id) and current_user.role != "admin":
        raise AuthorizationError()

    # Get messages
    messages_query = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
    )

    # Count total
    count_result = await db.execute(select(func.count()).select_from(messages_query.subquery()))
    total = count_result.scalar() or 0

    # Pagination
    offset = (page - 1) * page_size
    messages_query = messages_query.offset(offset).limit(page_size)

    messages_result = await db.execute(messages_query)
    messages = list(messages_result.scalars().all())

    # Mark messages as read
    unread_ids = [
        m.id for m in messages
        if not m.is_read and m.sender_id != current_user.id
    ]
    if unread_ids:
        await db.execute(
            Message.__table__.update()
            .where(Message.id.in_(unread_ids))
            .values(is_read=True, read_at=datetime.now(UTC))
        )

    return ConversationMessagesResponse(
        conversation=ConversationResponse.model_validate(conversation),
        messages=[MessageResponse.model_validate(m) for m in reversed(messages)],  # Oldest first
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/{conversation_id}/messages", response_model=MessageResponse, status_code=201)
async def send_message(
    conversation_id: UUID,
    message_data: MessageCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Message:
    """Send a message in a conversation."""
    # Get conversation
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise NotFoundError("Conversation", str(conversation_id))

    # Check permission
    if current_user.id not in (conversation.guest_id, conversation.host_id):
        raise AuthorizationError()

    # Create message
    message = Message(
        conversation_id=conversation_id,
        sender_id=current_user.id,
        content=message_data.content,
        message_type=message_data.message_type,
        image_url=message_data.image_url,
    )
    db.add(message)

    # Update conversation timestamp
    conversation.last_message_at = datetime.now(UTC)

    await db.flush()
    return message


@router.post("/start", response_model=ConversationResponse, status_code=201)
async def start_conversation(
    listing_id: UUID,
    message_data: MessageCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Conversation:
    """Start a new conversation about a listing."""
    # Get listing
    result = await db.execute(select(Listing).where(Listing.id == listing_id))
    listing = result.scalar_one_or_none()
    if not listing or listing.status != "approved":
        raise NotFoundError("Listing", str(listing_id))

    # Can't message yourself
    if listing.host_id == current_user.id:
        raise ValidationError("You cannot message yourself")

    # Check for existing conversation
    existing = await db.execute(
        select(Conversation).where(
            Conversation.listing_id == listing_id,
            Conversation.guest_id == current_user.id,
            Conversation.booking_id.is_(None),
        )
    )
    conversation = existing.scalar_one_or_none()

    if not conversation:
        # Create new conversation
        conversation = Conversation(
            listing_id=listing_id,
            guest_id=current_user.id,
            host_id=listing.host_id,
            last_message_at=datetime.now(UTC),
        )
        db.add(conversation)
        await db.flush()

    # Add first message
    message = Message(
        conversation_id=conversation.id,
        sender_id=current_user.id,
        content=message_data.content,
        message_type=message_data.message_type,
    )
    db.add(message)
    conversation.last_message_at = datetime.now(UTC)

    await db.flush()
    return conversation


@router.patch("/{conversation_id}/read", status_code=204)
async def mark_messages_read(
    conversation_id: UUID,
    request: MarkReadRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Mark messages as read."""
    # Verify access
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise NotFoundError("Conversation", str(conversation_id))

    if current_user.id not in (conversation.guest_id, conversation.host_id):
        raise AuthorizationError()

    # Mark messages as read
    query = (
        Message.__table__.update()
        .where(
            Message.conversation_id == conversation_id,
            Message.sender_id != current_user.id,
            Message.is_read == False,  # noqa: E712
        )
        .values(is_read=True, read_at=datetime.now(UTC))
    )

    if request.message_ids:
        query = query.where(Message.id.in_(request.message_ids))

    await db.execute(query)
