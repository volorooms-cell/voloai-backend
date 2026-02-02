"""Payment endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from datetime import UTC, datetime

from app.api.deps import get_current_active_user, get_current_admin, get_db
from app.core.exceptions import NotFoundError, PaymentError, ValidationError
from app.domain.payment_state import assert_payment_transition
from app.models.booking import Booking
from app.models.payment import HostPayout, Payment, Refund
from app.models.user import User
from app.schemas.payment import (
    PaymentCreate,
    PaymentIntentResponse,
    PaymentRefundRequest,
    PaymentResponse,
    PaymentStatusResponse,
    RefundResponse,
)
from app.core.idempotency import IdempotencyError, check_idempotency, generate_idempotency_key, store_idempotency_result
from app.services.audit_service import audit_service
from app.services.gateway_service import gateway_service
from app.services.settlement_service import settlement_service

router = APIRouter()


@router.post("/initiate", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
async def initiate_payment(
    payment_data: PaymentCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Payment:
    """Initiate a payment for a booking."""
    # Get booking
    result = await db.execute(select(Booking).where(Booking.id == payment_data.booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise NotFoundError("Booking", str(payment_data.booking_id))

    # Verify user is the guest
    if booking.guest_id != current_user.id:
        raise ValidationError("You can only pay for your own bookings")

    # Check booking status
    if booking.payment_status == "paid":
        raise ValidationError("Booking is already paid")
    if booking.status == "cancelled":
        raise ValidationError("Cannot pay for a cancelled booking")

    # Check for existing pending payment
    existing = await db.execute(
        select(Payment).where(
            Payment.booking_id == booking.id,
            Payment.status.in_(["pending", "processing"]),
        )
    )
    if existing.scalar_one_or_none():
        raise ValidationError("A payment is already in progress for this booking")

    # Create payment record
    payment = Payment(
        booking_id=booking.id,
        user_id=current_user.id,
        amount=booking.total_price,
        currency=booking.currency,
        payment_method=payment_data.payment_method,
        status="pending",
    )
    db.add(payment)
    await db.flush()

    # Process based on payment method
    if payment_data.payment_method == "card":
        # In production: Create Stripe PaymentIntent
        payment.gateway = "stripe"
        payment.status = "processing"
    elif payment_data.payment_method in ("jazzcash", "easypaisa"):
        payment.gateway = payment_data.payment_method
        payment.status = "processing"
    elif payment_data.payment_method == "bank_transfer":
        payment.gateway = "manual"
        # Requires manual verification
    else:
        payment.gateway = payment_data.payment_method
        payment.status = "processing"

    return payment


@router.post("/stripe/create-intent", response_model=PaymentIntentResponse)
async def create_stripe_payment_intent(
    payment_data: PaymentCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Create a Stripe PaymentIntent for card payments."""
    from app.config import settings

    if not settings.stripe_secret_key:
        raise PaymentError("Card payments are not configured")

    # Get booking
    result = await db.execute(select(Booking).where(Booking.id == payment_data.booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise NotFoundError("Booking", str(payment_data.booking_id))

    if booking.guest_id != current_user.id:
        raise ValidationError("You can only pay for your own bookings")

    # Create payment record
    payment = Payment(
        booking_id=booking.id,
        user_id=current_user.id,
        amount=booking.total_price,
        currency=booking.currency,
        payment_method="card",
        gateway="stripe",
        status="pending",
    )
    db.add(payment)
    await db.flush()

    # In production: Create actual Stripe PaymentIntent
    # For now, return mock client_secret
    return {
        "client_secret": f"pi_mock_{payment.id}_secret",
        "payment_id": payment.id,
    }


@router.post("/webhook/stripe", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Handle Stripe webhook events."""
    # In production: Verify webhook signature and process events
    # Payment succeeded → update booking status
    # Payment failed → notify user
    return {"received": True}


@router.post("/webhook/jazzcash", status_code=status.HTTP_200_OK)
async def jazzcash_webhook(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Handle JazzCash callback."""
    return {"received": True}


@router.post("/webhook/easypaisa", status_code=status.HTTP_200_OK)
async def easypaisa_webhook(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Handle Easypaisa callback."""
    return {"received": True}


@router.get("/{payment_id}/status", response_model=PaymentStatusResponse)
async def get_payment_status(
    payment_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Check payment status."""
    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()
    if not payment:
        raise NotFoundError("Payment", str(payment_id))

    # Verify ownership
    if payment.user_id != current_user.id and current_user.role != "admin":
        raise NotFoundError("Payment", str(payment_id))

    # Get booking status
    booking_result = await db.execute(select(Booking).where(Booking.id == payment.booking_id))
    booking = booking_result.scalar_one()

    return {
        "payment_id": payment.id,
        "status": payment.status,
        "booking_status": booking.status,
        "message": _get_status_message(payment.status),
    }


@router.post("/{payment_id}/mark-paid", response_model=PaymentResponse)
async def mark_payment_paid(
    payment_id: UUID,
    current_user: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Payment:
    """Mark payment as paid and update booking (admin only)."""
    # Idempotency check
    idem_key = generate_idempotency_key("payment_mark_paid", payment_id)
    if check_idempotency(idem_key):
        raise IdempotencyError("payment_mark_paid", str(payment_id))

    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()
    if not payment:
        raise NotFoundError("Payment", str(payment_id))

    # Validate payment state transition
    old_status = payment.status
    assert_payment_transition(payment.status, "completed")

    # Get booking for cross-domain validation
    booking_result = await db.execute(select(Booking).where(Booking.id == payment.booking_id))
    booking = booking_result.scalar_one()

    # Cross-domain rule: cannot pay for a cancelled booking
    if booking.status == "cancelled":
        raise ValidationError("Cannot mark payment as paid for a cancelled booking")

    # Update payment
    payment.status = "completed"
    payment.completed_at = datetime.now(UTC)

    # Update booking payment status
    booking.payment_status = "paid"

    # Record in settlement ledger
    await settlement_service.record_payment_received(db, payment, booking)

    # Audit log
    await audit_service.log_payment_action(
        db=db,
        user_id=current_user.id,
        action="payment_mark_paid",
        payment_id=payment_id,
        old_status=old_status,
        new_status="completed",
        amount=payment.amount,
    )

    # Store idempotency result
    store_idempotency_result(idem_key, {"payment_id": str(payment_id)})

    return payment


@router.post("/{payment_id}/refund", response_model=RefundResponse)
async def refund_payment(
    payment_id: UUID,
    request: PaymentRefundRequest,
    current_user: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Refund:
    """Refund a payment (admin only)."""
    # Idempotency check (include amount in key to allow multiple partial refunds)
    idem_key = generate_idempotency_key(
        "refund_create", payment_id, {"amount": request.amount, "reason": request.reason}
    )
    if check_idempotency(idem_key):
        raise IdempotencyError("refund_create", str(payment_id))

    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()
    if not payment:
        raise NotFoundError("Payment", str(payment_id))

    # Validate payment state transition
    assert_payment_transition(payment.status, "refunded")

    # Get booking
    booking_result = await db.execute(select(Booking).where(Booking.id == payment.booking_id))
    booking = booking_result.scalar_one()

    # Determine refund amount (full if not specified)
    refund_amount = request.amount if request.amount else payment.amount

    if refund_amount > payment.amount:
        raise ValidationError("Refund amount exceeds payment amount")

    # Check for existing refunds
    existing_refunds = await db.execute(
        select(Refund).where(Refund.payment_id == payment_id)
    )
    total_refunded = sum(r.amount for r in existing_refunds.scalars().all())

    if total_refunded + refund_amount > payment.amount:
        raise ValidationError(
            f"Total refunds ({total_refunded + refund_amount}) would exceed payment amount ({payment.amount})"
        )

    # Execute refund via gateway (if gateway transaction exists)
    gateway_refund_id = None
    if payment.gateway and payment.gateway_transaction_id:
        refund_result = await gateway_service.process_refund(
            gateway_type=payment.gateway,
            transaction_id=payment.gateway_transaction_id,
            amount=refund_amount,
            reason=request.reason,
        )
        if refund_result.success:
            gateway_refund_id = refund_result.refund_id

    # Create refund record
    refund = Refund(
        booking_id=booking.id,
        payment_id=payment.id,
        amount=refund_amount,
        reason=request.reason,
        status="approved",
        processed_by=current_user.id,
        processed_at=datetime.now(UTC),
        gateway_refund_id=gateway_refund_id,
    )
    db.add(refund)
    await db.flush()

    # Record in settlement ledger
    await settlement_service.record_refund_issued(db, refund, booking, payment)

    # Update payment status
    payment.status = "refunded"

    # Update booking
    booking.refund_amount = total_refunded + refund_amount
    is_full_refund = (total_refunded + refund_amount) >= booking.total_price
    booking.payment_status = "refunded" if is_full_refund else "partially_refunded"

    # Handle host payout reversal/reduction
    payout_result = await db.execute(
        select(HostPayout).where(HostPayout.booking_id == booking.id)
    )
    payout = payout_result.scalar_one_or_none()
    if payout:
        if is_full_refund:
            # Full refund - reverse the payout entirely
            if payout.status in ("pending", "eligible"):
                payout.status = "reversed"
            elif payout.status == "released":
                # Already released - mark as reversed (requires clawback)
                payout.status = "reversed"
        else:
            # Partial refund - reduce payout amount proportionally
            # Calculate commission on refund amount
            commission_rate = booking.commission_rate / 100
            refund_commission = int(refund_amount * float(commission_rate))
            payout_reduction = refund_amount - refund_commission
            payout.amount = max(0, payout.amount - payout_reduction)

    # Audit log
    await audit_service.log_refund_action(
        db=db,
        user_id=current_user.id,
        action="refund_create",
        refund_id=refund.id,
        payment_id=payment_id,
        amount=refund_amount,
        reason=request.reason,
    )

    # Store idempotency result
    store_idempotency_result(idem_key, {"refund_id": str(refund.id)})

    await db.flush()
    return refund


def _get_status_message(status: str) -> str:
    """Get human-readable status message."""
    messages = {
        "pending": "Payment is pending",
        "processing": "Payment is being processed",
        "completed": "Payment completed successfully",
        "failed": "Payment failed. Please try again.",
        "refunded": "Payment has been refunded",
    }
    return messages.get(status, "Unknown status")
