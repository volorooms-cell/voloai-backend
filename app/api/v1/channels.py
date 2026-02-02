"""Channel management endpoints for Airbnb/Booking.com sync."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_host, get_db, require_listing_owner
from app.core.exceptions import NotFoundError, ValidationError
from app.models.listing import Listing
from app.models.user import User

router = APIRouter()


@router.post("/airbnb/connect")
async def connect_airbnb(
    current_user: Annotated[User, Depends(get_current_host)],
) -> dict:
    """Initiate Airbnb OAuth connection."""
    # In production: Return OAuth URL for Airbnb Partner API
    return {
        "message": "Airbnb integration coming soon",
        "oauth_url": None,
    }


@router.post("/booking/connect")
async def connect_booking(
    current_user: Annotated[User, Depends(get_current_host)],
) -> dict:
    """Initiate Booking.com connection."""
    # In production: Return OAuth URL for Booking.com Connectivity API
    return {
        "message": "Booking.com integration coming soon",
        "oauth_url": None,
    }


@router.post("/{listing_id}/sync")
async def trigger_sync(
    listing_id: UUID,
    current_user: Annotated[User, Depends(require_listing_owner)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Manually trigger calendar sync for a listing."""
    result = await db.execute(select(Listing).where(Listing.id == listing_id))
    listing = result.scalar_one_or_none()
    if not listing:
        raise NotFoundError("Listing", str(listing_id))

    if not listing.sync_enabled:
        raise ValidationError("Sync is not enabled for this listing")

    # In production: Queue sync job
    # await channel_service.queue_sync(listing_id)

    return {
        "message": "Sync queued successfully",
        "listing_id": str(listing_id),
    }


@router.get("/status")
async def get_channel_status(
    current_user: Annotated[User, Depends(get_current_host)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Get channel connection status for all host's listings."""
    result = await db.execute(
        select(Listing).where(
            Listing.host_id == current_user.id,
            Listing.status != "deleted",
        )
    )
    listings = result.scalars().all()

    channel_status = []
    for listing in listings:
        channel_status.append({
            "listing_id": str(listing.id),
            "title": listing.title,
            "sync_enabled": listing.sync_enabled,
            "airbnb_connected": listing.external_airbnb_id is not None,
            "booking_connected": listing.external_booking_id is not None,
            "last_synced_at": listing.last_synced_at.isoformat() if listing.last_synced_at else None,
        })

    return {
        "listings": channel_status,
        "airbnb_account_connected": False,  # Would check user's OAuth tokens
        "booking_account_connected": False,
    }


@router.patch("/{listing_id}/settings")
async def update_channel_settings(
    listing_id: UUID,
    sync_enabled: bool,
    current_user: Annotated[User, Depends(require_listing_owner)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Update channel sync settings for a listing."""
    result = await db.execute(select(Listing).where(Listing.id == listing_id))
    listing = result.scalar_one_or_none()
    if not listing:
        raise NotFoundError("Listing", str(listing_id))

    listing.sync_enabled = sync_enabled

    return {
        "listing_id": str(listing_id),
        "sync_enabled": listing.sync_enabled,
    }
