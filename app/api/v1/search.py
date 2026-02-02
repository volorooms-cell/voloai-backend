"""Search endpoints for listing discovery."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db
from app.models.booking import CalendarBlock
from app.models.listing import Listing, ListingAmenity
from app.schemas.listing import ListingResponse, ListingSearchParams, ListingSearchResponse

router = APIRouter()


@router.get("/", response_model=ListingSearchResponse)
async def search_listings(
    db: Annotated[AsyncSession, Depends(get_db)],
    city: str | None = None,
    check_in: str | None = None,
    check_out: str | None = None,
    guests: int = Query(default=1, ge=1, le=20),
    listing_type: list[str] | None = Query(default=None),
    min_price: int | None = Query(default=None, ge=0),
    max_price: int | None = Query(default=None, ge=0),
    instant_booking: bool | None = None,
    bedrooms_min: int | None = Query(default=None, ge=0),
    bathrooms_min: float | None = Query(default=None, ge=0),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: str = Query(default="relevance", pattern="^(relevance|price_low|price_high|rating)$"),
) -> ListingSearchResponse:
    """Search for listings with filters."""
    from datetime import date

    # Base query - only approved listings
    query = (
        select(Listing)
        .where(Listing.status == "approved")
        .options(selectinload(Listing.photos))
    )

    # Apply filters
    filters = []

    # City filter
    if city:
        filters.append(func.lower(Listing.city).contains(func.lower(city)))

    # Guest capacity
    filters.append(Listing.max_guests >= guests)

    # Listing type
    if listing_type:
        filters.append(Listing.listing_type.in_(listing_type))

    # Price range (convert to paisa)
    if min_price is not None:
        filters.append(Listing.base_price_per_night >= min_price * 100)
    if max_price is not None:
        filters.append(Listing.base_price_per_night <= max_price * 100)

    # Instant booking
    if instant_booking is not None:
        filters.append(Listing.instant_booking == instant_booking)

    # Bedrooms
    if bedrooms_min is not None:
        filters.append(Listing.bedrooms >= bedrooms_min)

    # Bathrooms
    if bathrooms_min is not None:
        filters.append(Listing.bathrooms >= bathrooms_min)

    if filters:
        query = query.where(and_(*filters))

    # Date availability filter
    if check_in and check_out:
        try:
            check_in_date = date.fromisoformat(check_in)
            check_out_date = date.fromisoformat(check_out)

            # Subquery to find listings with conflicting blocks
            blocked_listings = (
                select(CalendarBlock.listing_id)
                .where(
                    or_(
                        and_(
                            CalendarBlock.start_date <= check_in_date,
                            CalendarBlock.end_date > check_in_date,
                        ),
                        and_(
                            CalendarBlock.start_date < check_out_date,
                            CalendarBlock.end_date >= check_out_date,
                        ),
                        and_(
                            CalendarBlock.start_date >= check_in_date,
                            CalendarBlock.end_date <= check_out_date,
                        ),
                    )
                )
                .distinct()
            )
            query = query.where(~Listing.id.in_(blocked_listings))

            # Min nights check
            nights = (check_out_date - check_in_date).days
            query = query.where(
                and_(Listing.min_nights <= nights, Listing.max_nights >= nights)
            )
        except ValueError:
            pass  # Invalid date format, skip filter

    # Sorting
    if sort_by == "price_low":
        query = query.order_by(Listing.base_price_per_night.asc())
    elif sort_by == "price_high":
        query = query.order_by(Listing.base_price_per_night.desc())
    else:
        # Default: relevance (by created date for now, could add rating later)
        query = query.order_by(Listing.created_at.desc())

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    # Execute
    result = await db.execute(query)
    listings = list(result.scalars().all())

    return ListingSearchResponse(
        listings=[ListingResponse.model_validate(l) for l in listings],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get("/autocomplete")
async def location_autocomplete(
    q: str = Query(..., min_length=2, max_length=100),
    db: Annotated[AsyncSession, Depends(get_db)] = None,
) -> list[dict[str, str]]:
    """Autocomplete for location search."""
    # Get unique cities from approved listings
    result = await db.execute(
        select(Listing.city)
        .where(
            Listing.status == "approved",
            func.lower(Listing.city).contains(func.lower(q)),
        )
        .distinct()
        .limit(10)
    )
    cities = result.scalars().all()
    return [{"type": "city", "value": city, "display": f"{city}, Pakistan"} for city in cities]


@router.get("/filters")
async def get_available_filters(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Get available filter options."""
    from app.models.listing import Amenity

    # Get unique listing types
    listing_types_result = await db.execute(
        select(Listing.listing_type)
        .where(Listing.status == "approved")
        .distinct()
    )
    listing_types = listing_types_result.scalars().all()

    # Get unique cities
    cities_result = await db.execute(
        select(Listing.city).where(Listing.status == "approved").distinct()
    )
    cities = cities_result.scalars().all()

    # Get price range
    price_result = await db.execute(
        select(
            func.min(Listing.base_price_per_night),
            func.max(Listing.base_price_per_night),
        ).where(Listing.status == "approved")
    )
    min_price, max_price = price_result.one()

    # Get amenities
    amenities_result = await db.execute(select(Amenity).order_by(Amenity.category, Amenity.name))
    amenities = amenities_result.scalars().all()

    return {
        "listing_types": [
            {"value": lt, "label": lt.replace("_", " ").title()}
            for lt in listing_types
        ],
        "cities": sorted(cities),
        "price_range": {
            "min": (min_price or 0) // 100,  # Convert paisa to PKR
            "max": (max_price or 100000) // 100,
            "currency": "PKR",
        },
        "amenities": [
            {"id": str(a.id), "name": a.name, "category": a.category, "icon": a.icon}
            for a in amenities
        ],
        "cancellation_policies": [
            {"value": "flexible", "label": "Flexible"},
            {"value": "moderate", "label": "Moderate"},
            {"value": "strict", "label": "Strict"},
            {"value": "super_strict", "label": "Super Strict"},
        ],
    }
