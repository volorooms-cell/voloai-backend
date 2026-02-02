"""Webhook endpoints for payment gateways."""

from datetime import UTC, datetime

from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.config import settings
from app.domain.payment_state import assert_payment_transition
from app.models.booking import Booking
from app.models.payment import Payment

router = APIRouter()


@router.post("/stripe", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(None, alias="Stripe-Signature"),
) -> dict:
    """Handle Stripe webhook events."""
    import stripe

    if not settings.stripe_secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe is not configured",
        )

    if not settings.stripe_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe webhook secret is not configured",
        )

    # Get raw body for signature verification
    payload = await request.body()

    # Verify webhook signature
    try:
        event = stripe.Webhook.construct_event(
            payload,
            stripe_signature,
            settings.stripe_webhook_secret,
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payload",
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid signature",
        )

    # Get database session
    from app.core.database import async_session_maker

    async with async_session_maker() as db:
        await _handle_stripe_event(db, event)
        await db.commit()

    return {"received": True}


async def _handle_stripe_event(db: AsyncSession, event: dict) -> None:
    """Process Stripe event and update payment/booking status."""
    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "payment_intent.succeeded":
        await _handle_payment_succeeded(db, data)
    elif event_type == "payment_intent.payment_failed":
        await _handle_payment_failed(db, data)


async def _handle_payment_succeeded(db: AsyncSession, data: dict) -> None:
    """Handle successful payment."""
    payment_intent_id = data["id"]

    # Find payment by gateway_transaction_id
    result = await db.execute(
        select(Payment).where(Payment.gateway_transaction_id == payment_intent_id)
    )
    payment = result.scalar_one_or_none()
    if not payment:
        return

    # Validate and update payment status
    try:
        assert_payment_transition(payment.status, "completed")
    except Exception:
        return  # Already completed or invalid state

    payment.status = "completed"
    payment.completed_at = datetime.now(UTC)
    payment.gateway_response = data

    # Update booking payment status
    booking_result = await db.execute(
        select(Booking).where(Booking.id == payment.booking_id)
    )
    booking = booking_result.scalar_one_or_none()
    if booking and booking.status != "cancelled":
        booking.payment_status = "paid"


async def _handle_payment_failed(db: AsyncSession, data: dict) -> None:
    """Handle failed payment."""
    payment_intent_id = data["id"]

    # Find payment by gateway_transaction_id
    result = await db.execute(
        select(Payment).where(Payment.gateway_transaction_id == payment_intent_id)
    )
    payment = result.scalar_one_or_none()
    if not payment:
        return

    # Validate and update payment status
    try:
        assert_payment_transition(payment.status, "failed")
    except Exception:
        return  # Already failed or invalid state

    payment.status = "failed"
    payment.gateway_response = data
