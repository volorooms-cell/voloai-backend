"""Listing endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import (
    get_current_active_user,
    get_current_host,
    get_db,
    get_optional_user,
    require_listing_access,
    require_listing_owner,
)
from app.core.exceptions import NotFoundError, ValidationError
from app.models.listing import (
    Listing,
    ListingAmenity,
    ListingPhoto,
)
from app.models.user import User
from app.schemas.listing import (
    CalendarBlockCreate,
    CalendarBlockResponse,
    DirectLinkResponse,
    ListingCreate,
    ListingPhotoCreate,
    ListingPhotoResponse,
    ListingResponse,
    ListingUpdate,
)
from app.utils.booking_number import generate_slug

router = APIRouter()


@router.post("/", response_model=ListingResponse, status_code=status.HTTP_201_CREATED)
async def create_listing(
    listing_data: ListingCreate,
    current_user: Annotated[User, Depends(get_current_host)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Listing:
    """Create a new listing."""
    # Convert prices to paisa (smallest unit)
    base_price_paisa = listing_data.base_price_per_night * 100
    cleaning_fee_paisa = listing_data.cleaning_fee * 100

    # Generate direct booking slug
    slug = await generate_slug(db)

    listing = Listing(
        host_id=current_user.id,
        title=listing_data.title,
        description=listing_data.description,
        listing_type=listing_data.listing_type,
        property_type=listing_data.property_type,
        address_line1=listing_data.address_line1,
        address_line2=listing_data.address_line2,
        city=listing_data.city,
        state_province=listing_data.state_province,
        postal_code=listing_data.postal_code,
        country=listing_data.country,
        latitude=listing_data.latitude,
        longitude=listing_data.longitude,
        max_guests=listing_data.max_guests,
        bedrooms=listing_data.bedrooms,
        beds=listing_data.beds,
        bathrooms=listing_data.bathrooms,
        base_price_per_night=base_price_paisa,
        cleaning_fee=cleaning_fee_paisa,
        currency=listing_data.currency,
        cancellation_policy=listing_data.cancellation_policy,
        check_in_time=listing_data.check_in_time,
        check_out_time=listing_data.check_out_time,
        min_nights=listing_data.min_nights,
        max_nights=listing_data.max_nights,
        instant_booking=listing_data.instant_booking,
        direct_booking_slug=slug,
        status="draft",
    )
    db.add(listing)
    await db.flush()

    # Add amenities
    for amenity_id in listing_data.amenity_ids:
        listing_amenity = ListingAmenity(listing_id=listing.id, amenity_id=amenity_id)
        db.add(listing_amenity)

    await db.flush()

    # Reload with relationships
    result = await db.execute(
        select(Listing)
        .where(Listing.id == listing.id)
        .options(
            selectinload(Listing.photos),
            selectinload(Listing.house_rules),
            selectinload(Listing.pricing_rules),
            selectinload(Listing.amenities).selectinload(ListingAmenity.amenity),
        )
    )
    return result.scalar_one()


@router.get("/", response_model=list[ListingResponse])
async def get_my_listings(
    current_user: Annotated[User, Depends(get_current_host)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: str | None = Query(None, alias="status"),
) -> list[Listing]:
    """Get all listings for the current host."""
    query = (
        select(Listing)
        .where(Listing.host_id == current_user.id)
        .options(
            selectinload(Listing.photos),
            selectinload(Listing.house_rules),
            selectinload(Listing.pricing_rules),
            selectinload(Listing.amenities).selectinload(ListingAmenity.amenity),
        )
    )
    if status_filter:
        query = query.where(Listing.status == status_filter)
    query = query.order_by(Listing.created_at.desc())

    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{listing_id}", response_model=ListingResponse)
async def get_listing(
    listing_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User | None, Depends(get_optional_user)] = None,
) -> Listing:
    """Get a listing by ID."""
    result = await db.execute(
        select(Listing)
        .where(Listing.id == listing_id)
        .options(
            selectinload(Listing.photos),
            selectinload(Listing.house_rules),
            selectinload(Listing.pricing_rules),
            selectinload(Listing.amenities).selectinload(ListingAmenity.amenity),
        )
    )
    listing = result.scalar_one_or_none()
    if not listing:
        raise NotFoundError("Listing", str(listing_id))

    # Only show approved listings to non-owners
    if listing.status != "approved":
        if not current_user or (
            current_user.id != listing.host_id and current_user.role != "admin"
        ):
            raise NotFoundError("Listing", str(listing_id))

    return listing


@router.patch("/{listing_id}", response_model=ListingResponse)
async def update_listing(
    listing_id: UUID,
    updates: ListingUpdate,
    current_user: Annotated[User, Depends(require_listing_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Listing:
    """Update a listing."""
    result = await db.execute(
        select(Listing)
        .where(Listing.id == listing_id)
        .options(
            selectinload(Listing.photos),
            selectinload(Listing.house_rules),
            selectinload(Listing.pricing_rules),
            selectinload(Listing.amenities).selectinload(ListingAmenity.amenity),
        )
    )
    listing = result.scalar_one_or_none()
    if not listing:
        raise NotFoundError("Listing", str(listing_id))

    update_data = updates.model_dump(exclude_unset=True)

    # Convert prices to paisa if provided
    if "base_price_per_night" in update_data:
        update_data["base_price_per_night"] *= 100
    if "cleaning_fee" in update_data:
        update_data["cleaning_fee"] *= 100

    for field, value in update_data.items():
        setattr(listing, field, value)

    return listing


@router.delete("/{listing_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_listing(
    listing_id: UUID,
    current_user: Annotated[User, Depends(require_listing_owner)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a listing (soft delete)."""
    result = await db.execute(select(Listing).where(Listing.id == listing_id))
    listing = result.scalar_one_or_none()
    if not listing:
        raise NotFoundError("Listing", str(listing_id))

    # Soft delete
    listing.status = "deleted"


@router.post("/{listing_id}/submit", response_model=ListingResponse)
async def submit_for_approval(
    listing_id: UUID,
    current_user: Annotated[User, Depends(require_listing_owner)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Listing:
    """Submit listing for approval."""
    result = await db.execute(
        select(Listing).where(Listing.id == listing_id).options(selectinload(Listing.photos))
    )
    listing = result.scalar_one_or_none()
    if not listing:
        raise NotFoundError("Listing", str(listing_id))

    if listing.status not in ("draft", "rejected"):
        raise ValidationError("Listing cannot be submitted in current status")

    # Validate required fields
    if not listing.photos:
        raise ValidationError("At least one photo is required")

    listing.status = "pending_approval"
    return listing


@router.post("/{listing_id}/photos", response_model=ListingPhotoResponse, status_code=status.HTTP_201_CREATED)
async def add_photo(
    listing_id: UUID,
    photo_data: ListingPhotoCreate,
    current_user: Annotated[User, Depends(require_listing_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ListingPhoto:
    """Add a photo to a listing."""
    # Verify listing exists
    result = await db.execute(select(Listing).where(Listing.id == listing_id))
    listing = result.scalar_one_or_none()
    if not listing:
        raise NotFoundError("Listing", str(listing_id))

    # Get current max sort order
    result = await db.execute(
        select(ListingPhoto)
        .where(ListingPhoto.listing_id == listing_id)
        .order_by(ListingPhoto.sort_order.desc())
    )
    last_photo = result.scalar_one_or_none()
    next_order = (last_photo.sort_order + 1) if last_photo else 0

    # If this is the first photo or marked as cover, update others
    if photo_data.is_cover:
        await db.execute(
            ListingPhoto.__table__.update()
            .where(ListingPhoto.listing_id == listing_id)
            .values(is_cover=False)
        )

    photo = ListingPhoto(
        listing_id=listing_id,
        url=photo_data.url,
        caption=photo_data.caption,
        sort_order=next_order,
        is_cover=photo_data.is_cover or next_order == 0,
    )
    db.add(photo)
    await db.flush()
    return photo


@router.delete("/{listing_id}/photos/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_photo(
    listing_id: UUID,
    photo_id: UUID,
    current_user: Annotated[User, Depends(require_listing_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a photo from a listing."""
    result = await db.execute(
        select(ListingPhoto).where(
            ListingPhoto.id == photo_id, ListingPhoto.listing_id == listing_id
        )
    )
    photo = result.scalar_one_or_none()
    if not photo:
        raise NotFoundError("Photo", str(photo_id))

    await db.delete(photo)


@router.get("/{listing_id}/calendar", response_model=list[CalendarBlockResponse])
async def get_calendar(
    listing_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list:
    """Get calendar blocks for a listing."""
    from app.models.booking import CalendarBlock

    result = await db.execute(
        select(CalendarBlock)
        .where(CalendarBlock.listing_id == listing_id)
        .order_by(CalendarBlock.start_date)
    )
    return list(result.scalars().all())


@router.post("/{listing_id}/calendar", response_model=CalendarBlockResponse, status_code=status.HTTP_201_CREATED)
async def create_calendar_block(
    listing_id: UUID,
    block_data: CalendarBlockCreate,
    current_user: Annotated[User, Depends(require_listing_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create a manual calendar block."""
    from app.models.booking import CalendarBlock

    # Verify listing exists
    result = await db.execute(select(Listing).where(Listing.id == listing_id))
    if not result.scalar_one_or_none():
        raise NotFoundError("Listing", str(listing_id))

    block = CalendarBlock(
        listing_id=listing_id,
        start_date=block_data.start_date,
        end_date=block_data.end_date,
        block_type="manual",
        notes=block_data.notes,
    )
    db.add(block)
    await db.flush()
    return block


@router.get("/{listing_id}/direct-link", response_model=DirectLinkResponse)
async def get_direct_link(
    listing_id: UUID,
    current_user: Annotated[User, Depends(require_listing_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Get direct booking link and QR code for a listing."""
    result = await db.execute(select(Listing).where(Listing.id == listing_id))
    listing = result.scalar_one_or_none()
    if not listing:
        raise NotFoundError("Listing", str(listing_id))

    base_url = "https://voloai.pk"
    return {
        "direct_booking_slug": listing.direct_booking_slug,
        "url": f"{base_url}/book/{listing.direct_booking_slug}",
        "qr_code_url": f"{base_url}/api/v1/listings/{listing_id}/qr-code",
    }
