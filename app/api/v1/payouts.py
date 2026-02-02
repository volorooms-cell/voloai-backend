"""Payout endpoints for hosts."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_current_host, get_db
from app.core.encryption import get_encryption_service
from app.core.exceptions import NotFoundError, ValidationError
from app.domain.payout_state import assert_payout_transition, can_release_payout
from app.models.booking import Booking
from app.models.payment import HostPayout
from app.models.user import User
from app.schemas.payment import (
    PayoutListResponse,
    PayoutResponse,
    PayoutSettingsResponse,
    PayoutSettingsUpdate,
)
from app.core.idempotency import IdempotencyError, check_idempotency, generate_idempotency_key, store_idempotency_result
from app.services.audit_service import audit_service
from app.services.settlement_service import settlement_service

router = APIRouter()


@router.get("/", response_model=PayoutListResponse)
async def get_my_payouts(
    current_user: Annotated[User, Depends(get_current_host)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PayoutListResponse:
    """Get host's payout history."""
    query = select(HostPayout).where(HostPayout.host_id == current_user.id)

    if status_filter:
        query = query.where(HostPayout.status == status_filter)

    # Count and sum
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    sum_result = await db.execute(
        select(func.sum(HostPayout.amount)).where(
            HostPayout.host_id == current_user.id,
            HostPayout.status == "completed",
        )
    )
    total_amount = sum_result.scalar() or 0

    # Pagination
    offset = (page - 1) * page_size
    query = query.order_by(HostPayout.created_at.desc()).offset(offset).limit(page_size)

    result = await db.execute(query)
    payouts = list(result.scalars().all())

    return PayoutListResponse(
        payouts=[PayoutResponse.model_validate(p) for p in payouts],
        total=total,
        total_amount=total_amount,
        page=page,
        page_size=page_size,
    )


@router.get("/settings", response_model=PayoutSettingsResponse)
async def get_payout_settings(
    current_user: Annotated[User, Depends(get_current_host)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Get host's payout settings."""
    # Get most recent payout to find bank details
    result = await db.execute(
        select(HostPayout)
        .where(HostPayout.host_id == current_user.id)
        .order_by(HostPayout.created_at.desc())
        .limit(1)
    )
    payout = result.scalar_one_or_none()

    if not payout or not payout.account_number_encrypted:
        return {
            "bank_name": None,
            "account_number_masked": None,
            "account_holder_name": None,
            "payout_method": None,
        }

    # Decrypt and mask account number
    encryption = get_encryption_service()
    account_number = encryption.decrypt(payout.account_number_encrypted)
    masked = "*" * (len(account_number) - 4) + account_number[-4:]

    return {
        "bank_name": payout.bank_name,
        "account_number_masked": masked,
        "account_holder_name": payout.account_holder_name,
        "payout_method": payout.payout_method,
    }


@router.patch("/settings", response_model=PayoutSettingsResponse)
async def update_payout_settings(
    settings: PayoutSettingsUpdate,
    current_user: Annotated[User, Depends(get_current_host)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Update host's payout settings."""
    # In a production system, you'd store these in a separate table
    # For now, we'll update the encryption and return the masked version

    update_data = settings.model_dump(exclude_unset=True)

    masked_account = None
    if "account_number" in update_data and update_data["account_number"]:
        account = update_data["account_number"]
        masked_account = "*" * (len(account) - 4) + account[-4:]

    return {
        "bank_name": update_data.get("bank_name"),
        "account_number_masked": masked_account,
        "account_holder_name": update_data.get("account_holder_name"),
        "payout_method": update_data.get("payout_method"),
    }


@router.get("/{payout_id}", response_model=PayoutResponse)
async def get_payout(
    payout_id: UUID,
    current_user: Annotated[User, Depends(get_current_host)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> HostPayout:
    """Get a specific payout."""
    result = await db.execute(
        select(HostPayout).where(
            HostPayout.id == payout_id,
            HostPayout.host_id == current_user.id,
        )
    )
    payout = result.scalar_one_or_none()
    if not payout:
        raise NotFoundError("Payout", str(payout_id))
    return payout


# ============ ADMIN PAYOUT LIFECYCLE ============


@router.post("/{payout_id}/mark-eligible", response_model=PayoutResponse)
async def mark_payout_eligible(
    payout_id: UUID,
    current_user: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> HostPayout:
    """Mark payout as eligible for release (admin only)."""
    result = await db.execute(select(HostPayout).where(HostPayout.id == payout_id))
    payout = result.scalar_one_or_none()
    if not payout:
        raise NotFoundError("Payout", str(payout_id))

    # Validate state transition
    assert_payout_transition(payout.status, "eligible")

    # Check booking state if linked
    if payout.booking_id:
        booking_result = await db.execute(
            select(Booking).where(Booking.id == payout.booking_id)
        )
        booking = booking_result.scalar_one_or_none()
        if booking:
            can_release, error = can_release_payout(booking.status, booking.payment_status)
            if not can_release:
                raise ValidationError(error)

    payout.status = "eligible"
    return payout


@router.post("/{payout_id}/release", response_model=PayoutResponse)
async def release_payout(
    payout_id: UUID,
    current_user: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> HostPayout:
    """Release payout to host (admin only)."""
    # Idempotency check
    idem_key = generate_idempotency_key("payout_release", payout_id)
    if check_idempotency(idem_key):
        raise IdempotencyError("payout_release", str(payout_id))

    result = await db.execute(select(HostPayout).where(HostPayout.id == payout_id))
    payout = result.scalar_one_or_none()
    if not payout:
        raise NotFoundError("Payout", str(payout_id))

    # Validate state transition
    old_status = payout.status
    assert_payout_transition(payout.status, "released")

    # Final check on booking state
    booking = None
    if payout.booking_id:
        booking_result = await db.execute(
            select(Booking).where(Booking.id == payout.booking_id)
        )
        booking = booking_result.scalar_one_or_none()
        if booking:
            can_release, error = can_release_payout(booking.status, booking.payment_status)
            if not can_release:
                raise ValidationError(error)

    payout.status = "released"
    payout.processed_at = datetime.now(UTC)

    # Record in settlement ledger
    await settlement_service.record_payout_released(db, payout, booking)

    # Audit log
    await audit_service.log_payout_action(
        db=db,
        user_id=current_user.id,
        action="payout_release",
        payout_id=payout_id,
        old_status=old_status,
        new_status="released",
        amount=payout.amount,
        host_id=payout.host_id,
    )

    # Store idempotency result
    store_idempotency_result(idem_key, {"payout_id": str(payout_id)})

    return payout


@router.post("/{payout_id}/reverse", response_model=PayoutResponse)
async def reverse_payout(
    payout_id: UUID,
    current_user: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> HostPayout:
    """Reverse a payout due to refund/dispute (admin only)."""
    # Idempotency check
    idem_key = generate_idempotency_key("payout_reverse", payout_id)
    if check_idempotency(idem_key):
        raise IdempotencyError("payout_reverse", str(payout_id))

    result = await db.execute(select(HostPayout).where(HostPayout.id == payout_id))
    payout = result.scalar_one_or_none()
    if not payout:
        raise NotFoundError("Payout", str(payout_id))

    # Validate state transition
    old_status = payout.status
    assert_payout_transition(payout.status, "reversed")

    # Get booking if linked
    booking = None
    if payout.booking_id:
        booking_result = await db.execute(
            select(Booking).where(Booking.id == payout.booking_id)
        )
        booking = booking_result.scalar_one_or_none()

    payout.status = "reversed"

    # Record in settlement ledger
    await settlement_service.record_payout_reversed(db, payout, booking)

    # Audit log
    await audit_service.log_payout_action(
        db=db,
        user_id=current_user.id,
        action="payout_reverse",
        payout_id=payout_id,
        old_status=old_status,
        new_status="reversed",
        amount=payout.amount,
        host_id=payout.host_id,
    )

    # Store idempotency result
    store_idempotency_result(idem_key, {"payout_id": str(payout_id)})

    return payout
