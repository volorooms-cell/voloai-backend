"""Booking endpoints."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_active_user,
    get_current_verified_user,
    get_db,
    require_booking_access,
    require_guest_booking_access,
    require_host_booking_access,
)
from app.core.exceptions import (
    DatesNotAvailable,
    ListingNotAvailable,
    NotFoundError,
    ValidationError,
)
from app.domain.booking_state import assert_booking_transition
from app.domain.cancellation_policy import calculate_refund_amount
from app.models.booking import Booking, BookingExtension, CalendarBlock
from app.models.listing import Listing
from app.models.payment import HostPayout
from app.models.user import User
from app.schemas.booking import (
    BookingCalculateRequest,
    BookingCalculateResponse,
    BookingCancelRequest,
    BookingConfirmRequest,
    BookingCreate,
    BookingExtensionCreate,
    BookingExtensionResponse,
    BookingListResponse,
    BookingPriceBreakdown,
    BookingResponse,
)
from app.services.commission_service import CommissionService
from app.services.settlement_service import settlement_service
from app.utils.booking_number import generate_booking_number

router = APIRouter()
commission_service = CommissionService()


async def check_availability(
    db: AsyncSession, listing_id: UUID, check_in, check_out, exclude_booking_id: UUID | None = None
) -> bool:
    """Check if dates are available for a listing."""
    query = select(CalendarBlock).where(
        CalendarBlock.listing_id == listing_id,
        or_(
            and_(
                CalendarBlock.start_date <= check_in,
                CalendarBlock.end_date > check_in,
            ),
            and_(
                CalendarBlock.start_date < check_out,
                CalendarBlock.end_date >= check_out,
            ),
            and_(
                CalendarBlock.start_date >= check_in,
                CalendarBlock.end_date <= check_out,
            ),
        ),
    )
    result = await db.execute(query)
    return result.scalar_one_or_none() is None


@router.post("/calculate", response_model=BookingCalculateResponse)
async def calculate_booking_price(
    request: BookingCalculateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BookingCalculateResponse:
    """Calculate booking price without creating a booking."""
    # Get listing
    result = await db.execute(select(Listing).where(Listing.id == request.listing_id))
    listing = result.scalar_one_or_none()
    if not listing or listing.status != "approved":
        return BookingCalculateResponse(
            available=False, unavailable_reason="Listing not available"
        )

    # Check guest capacity
    if request.guests > listing.max_guests:
        return BookingCalculateResponse(
            available=False,
            unavailable_reason=f"Maximum {listing.max_guests} guests allowed",
        )

    # Check min/max nights
    nights = (request.check_out - request.check_in).days
    if nights < listing.min_nights:
        return BookingCalculateResponse(
            available=False,
            unavailable_reason=f"Minimum stay is {listing.min_nights} nights",
        )
    if nights > listing.max_nights:
        return BookingCalculateResponse(
            available=False,
            unavailable_reason=f"Maximum stay is {listing.max_nights} nights",
        )

    # Check availability
    available = await check_availability(db, listing.id, request.check_in, request.check_out)
    if not available:
        return BookingCalculateResponse(
            available=False, unavailable_reason="Selected dates are not available"
        )

    # Calculate pricing
    pricing = commission_service.calculate_booking_amounts(
        source=request.source,
        nightly_rate=listing.base_price_per_night,
        nights=nights,
        cleaning_fee=listing.cleaning_fee,
    )

    return BookingCalculateResponse(
        available=True,
        price_breakdown=BookingPriceBreakdown(
            nightly_rate=listing.base_price_per_night,
            nights=nights,
            subtotal=pricing["subtotal"],
            cleaning_fee=pricing["cleaning_fee"],
            service_fee=pricing["service_fee"],
            taxes=0,
            total_price=pricing["total_price"],
            currency=listing.currency,
            commission_rate=pricing["commission_rate"],
            commission_amount=pricing["commission_amount"],
            host_payout_amount=pricing["host_payout_amount"],
        ),
    )


@router.post("/", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
async def create_booking(
    booking_data: BookingCreate,
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Booking:
    """Create a new booking."""
    # Get listing
    result = await db.execute(select(Listing).where(Listing.id == booking_data.listing_id))
    listing = result.scalar_one_or_none()
    if not listing or listing.status != "approved":
        raise ListingNotAvailable()

    # Prevent booking own listing
    if listing.host_id == current_user.id:
        raise ValidationError("You cannot book your own listing")

    # Check guest capacity
    total_guests = booking_data.adults + booking_data.children
    if total_guests > listing.max_guests:
        raise ValidationError(f"Maximum {listing.max_guests} guests allowed")

    # Check min/max nights
    nights = (booking_data.check_out - booking_data.check_in).days
    if nights < listing.min_nights:
        raise ValidationError(f"Minimum stay is {listing.min_nights} nights")
    if nights > listing.max_nights:
        raise ValidationError(f"Maximum stay is {listing.max_nights} nights")

    # Check availability
    available = await check_availability(
        db, listing.id, booking_data.check_in, booking_data.check_out
    )
    if not available:
        raise DatesNotAvailable()

    # Calculate pricing
    pricing = commission_service.calculate_booking_amounts(
        source=booking_data.source,
        nightly_rate=listing.base_price_per_night,
        nights=nights,
        cleaning_fee=listing.cleaning_fee,
    )

    # Generate booking number
    booking_number = await generate_booking_number(db)

    # Create booking
    booking = Booking(
        booking_number=booking_number,
        listing_id=listing.id,
        guest_id=current_user.id,
        host_id=listing.host_id,
        source=booking_data.source,
        commission_rate=pricing["commission_rate"],
        check_in=booking_data.check_in,
        check_out=booking_data.check_out,
        adults=booking_data.adults,
        children=booking_data.children,
        infants=booking_data.infants,
        nightly_rate=listing.base_price_per_night,
        subtotal=pricing["subtotal"],
        cleaning_fee=pricing["cleaning_fee"],
        service_fee=pricing["service_fee"],
        taxes=0,
        total_price=pricing["total_price"],
        currency=listing.currency,
        commission_amount=pricing["commission_amount"],
        host_payout_amount=pricing["host_payout_amount"],
        special_requests=booking_data.special_requests,
        status="confirmed" if listing.instant_booking else "pending",
    )
    db.add(booking)
    await db.flush()

    # Block calendar
    calendar_block = CalendarBlock(
        listing_id=listing.id,
        start_date=booking_data.check_in,
        end_date=booking_data.check_out,
        block_type="volo_booking",
    )
    db.add(calendar_block)

    # If instant booking, set confirmed timestamp
    if listing.instant_booking:
        booking.confirmed_at = datetime.now(UTC)

    await db.flush()
    return booking


@router.get("/", response_model=BookingListResponse)
async def get_my_bookings(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    role: str = Query(default="guest", pattern="^(guest|host)$"),
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> BookingListResponse:
    """Get bookings for the current user."""
    if role == "guest":
        query = select(Booking).where(Booking.guest_id == current_user.id)
    else:
        if current_user.role not in ("host", "admin"):
            raise ValidationError("You must be a host to view host bookings")
        query = select(Booking).where(Booking.host_id == current_user.id)

    if status_filter:
        query = query.where(Booking.status == status_filter)

    # Count total
    from sqlalchemy import func

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    # Pagination
    offset = (page - 1) * page_size
    query = query.order_by(Booking.created_at.desc()).offset(offset).limit(page_size)

    result = await db.execute(query)
    bookings = list(result.scalars().all())

    return BookingListResponse(
        bookings=[BookingResponse.model_validate(b) for b in bookings],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{booking_id}", response_model=BookingResponse)
async def get_booking(
    booking_id: UUID,
    current_user: Annotated[User, Depends(require_booking_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Booking:
    """Get a booking by ID."""
    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise NotFoundError("Booking", str(booking_id))
    return booking


@router.post("/{booking_id}/confirm", response_model=BookingResponse)
async def confirm_booking(
    booking_id: UUID,
    request: BookingConfirmRequest,
    current_user: Annotated[User, Depends(require_host_booking_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Booking:
    """Confirm a pending booking (host only)."""
    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise NotFoundError("Booking", str(booking_id))

    assert_booking_transition(booking.status, "confirmed")

    booking.status = "confirmed"
    booking.confirmed_at = datetime.now(UTC)
    return booking


@router.post("/{booking_id}/cancel", response_model=BookingResponse)
async def cancel_booking(
    booking_id: UUID,
    request: BookingCancelRequest,
    current_user: Annotated[User, Depends(require_booking_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Booking:
    """Cancel a booking."""
    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise NotFoundError("Booking", str(booking_id))

    assert_booking_transition(booking.status, "cancelled")

    # Get listing for cancellation policy
    listing_result = await db.execute(select(Listing).where(Listing.id == booking.listing_id))
    listing = listing_result.scalar_one()

    # Determine who is cancelling
    if current_user.id == booking.guest_id:
        cancelled_by = "guest"
    elif current_user.id == booking.host_id or current_user.role == "admin":
        cancelled_by = "host" if current_user.id == booking.host_id else "admin"
    else:
        cancelled_by = "admin"

    # Calculate refund based on cancellation policy (only if not already refunded)
    if booking.refund_amount == 0:
        # Host cancellation = full refund regardless of policy
        if cancelled_by == "host":
            booking.refund_amount = booking.total_price
        else:
            # Guest/admin cancellation uses listing's policy
            booking.refund_amount = calculate_refund_amount(
                policy=listing.cancellation_policy,
                check_in_date=booking.check_in,
                cancellation_date=datetime.now(UTC).date(),
                total_price=booking.total_price,
            )

    booking.status = "cancelled"
    booking.cancelled_by = cancelled_by
    booking.cancellation_reason = request.reason
    booking.cancelled_at = datetime.now(UTC)

    # Remove calendar block
    await db.execute(
        CalendarBlock.__table__.delete().where(
            CalendarBlock.listing_id == booking.listing_id,
            CalendarBlock.start_date == booking.check_in,
            CalendarBlock.end_date == booking.check_out,
            CalendarBlock.block_type == "volo_booking",
        )
    )

    return booking


@router.post("/{booking_id}/check-in", response_model=BookingResponse)
async def check_in_booking(
    booking_id: UUID,
    current_user: Annotated[User, Depends(require_host_booking_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Booking:
    """Mark guest as checked in (host only)."""
    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise NotFoundError("Booking", str(booking_id))

    assert_booking_transition(booking.status, "checked_in")

    if booking.payment_status != "paid":
        raise ValidationError("Payment must be completed before check-in")

    booking.status = "checked_in"
    return booking


@router.post("/{booking_id}/complete", response_model=BookingResponse)
async def complete_booking(
    booking_id: UUID,
    current_user: Annotated[User, Depends(require_host_booking_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Booking:
    """Mark booking as completed (host only)."""
    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise NotFoundError("Booking", str(booking_id))

    assert_booking_transition(booking.status, "completed")

    booking.status = "completed"
    booking.completed_at = datetime.now(UTC)

    # Create pending payout for host (if not already exists and payment is complete)
    if booking.payment_status == "paid":
        existing_payout = await db.execute(
            select(HostPayout).where(HostPayout.booking_id == booking_id)
        )
        if not existing_payout.scalar_one_or_none():
            payout = HostPayout(
                host_id=booking.host_id,
                booking_id=booking_id,
                amount=booking.host_payout_amount,
                currency=booking.currency,
                payout_date=booking.check_out,
                status="pending",
            )
            db.add(payout)

    # Create immutable financial snapshot for settlement/reconciliation
    await settlement_service.create_booking_snapshot(db, booking)

    return booking


@router.post("/{booking_id}/extend", response_model=BookingExtensionResponse, status_code=status.HTTP_201_CREATED)
async def request_extension(
    booking_id: UUID,
    request: BookingExtensionCreate,
    current_user: Annotated[User, Depends(require_guest_booking_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BookingExtension:
    """Request a booking extension (guest only)."""
    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise NotFoundError("Booking", str(booking_id))

    if booking.status not in ("confirmed", "completed"):
        raise InvalidBookingStatus("Booking must be confirmed to request extension")

    if request.new_check_out <= booking.check_out:
        raise ValidationError("New checkout must be after current checkout")

    # Check availability
    available = await check_availability(
        db, booking.listing_id, booking.check_out, request.new_check_out, exclude_booking_id=booking_id
    )
    if not available:
        raise DatesNotAvailable()

    # Calculate extension pricing
    additional_nights = (request.new_check_out - booking.check_out).days
    extension_pricing = commission_service.calculate_extension_commission(
        original_source=booking.source,
        additional_nights=additional_nights,
        nightly_rate=booking.nightly_rate,
    )

    # Get listing for instant booking check
    listing_result = await db.execute(select(Listing).where(Listing.id == booking.listing_id))
    listing = listing_result.scalar_one()

    extension = BookingExtension(
        booking_id=booking_id,
        original_check_out=booking.check_out,
        new_check_out=request.new_check_out,
        additional_nights=additional_nights,
        additional_amount=extension_pricing["additional_amount"],
        commission_amount=extension_pricing["commission_amount"],
        status="approved" if listing.instant_booking else "pending",
    )
    db.add(extension)
    await db.flush()

    # If instant booking, auto-approve
    if listing.instant_booking:
        extension.processed_at = datetime.now(UTC)
        booking.check_out = request.new_check_out
        booking.subtotal += extension.additional_amount
        booking.total_price += extension.additional_amount
        booking.commission_amount += extension.commission_amount
        booking.host_payout_amount += extension.additional_amount - extension.commission_amount

    return extension


@router.post("/{booking_id}/extend/approve", response_model=BookingExtensionResponse)
async def approve_extension(
    booking_id: UUID,
    current_user: Annotated[User, Depends(require_host_booking_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BookingExtension:
    """Approve a pending booking extension (host only)."""
    result = await db.execute(
        select(BookingExtension)
        .where(BookingExtension.booking_id == booking_id, BookingExtension.status == "pending")
        .order_by(BookingExtension.requested_at.desc())
    )
    extension = result.scalar_one_or_none()
    if not extension:
        raise NotFoundError("Pending extension for booking", str(booking_id))

    # Get booking
    booking_result = await db.execute(select(Booking).where(Booking.id == booking_id))
    booking = booking_result.scalar_one()

    # Approve and update booking
    extension.status = "approved"
    extension.processed_at = datetime.now(UTC)

    booking.check_out = extension.new_check_out
    booking.subtotal += extension.additional_amount
    booking.total_price += extension.additional_amount
    booking.commission_amount += extension.commission_amount
    booking.host_payout_amount += extension.additional_amount - extension.commission_amount

    return extension
