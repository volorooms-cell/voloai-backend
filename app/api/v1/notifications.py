"""Notification endpoints."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db
from app.core.exceptions import NotFoundError
from app.models.message import Notification
from app.models.user import User
from app.schemas.message import (
    NotificationListResponse,
    NotificationResponse,
    PushTokenRegister,
)

router = APIRouter()


@router.get("/", response_model=NotificationListResponse)
async def get_notifications(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    unread_only: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> NotificationListResponse:
    """Get user's notifications."""
    query = select(Notification).where(Notification.user_id == current_user.id)

    if unread_only:
        query = query.where(Notification.is_read == False)  # noqa: E712

    # Count total
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    # Count unread
    unread_result = await db.execute(
        select(func.count()).where(
            Notification.user_id == current_user.id,
            Notification.is_read == False,  # noqa: E712
        )
    )
    unread_count = unread_result.scalar() or 0

    # Pagination
    offset = (page - 1) * page_size
    query = query.order_by(Notification.created_at.desc()).offset(offset).limit(page_size)

    result = await db.execute(query)
    notifications = list(result.scalars().all())

    return NotificationListResponse(
        notifications=[NotificationResponse.model_validate(n) for n in notifications],
        total=total,
        unread_count=unread_count,
        page=page,
        page_size=page_size,
    )


@router.patch("/{notification_id}/read", status_code=204)
async def mark_notification_read(
    notification_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Mark a notification as read."""
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    notification = result.scalar_one_or_none()
    if not notification:
        raise NotFoundError("Notification", str(notification_id))

    notification.is_read = True
    notification.read_at = datetime.now(UTC)


@router.post("/read-all", status_code=204)
async def mark_all_read(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Mark all notifications as read."""
    await db.execute(
        Notification.__table__.update()
        .where(
            Notification.user_id == current_user.id,
            Notification.is_read == False,  # noqa: E712
        )
        .values(is_read=True, read_at=datetime.now(UTC))
    )


@router.post("/token", status_code=204)
async def register_push_token(
    request: PushTokenRegister,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Register push notification token."""
    current_user.push_token = request.token
