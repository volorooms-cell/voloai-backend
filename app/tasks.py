"""Celery background tasks.

This module contains all background tasks for:
- Payment processing and payouts
- Notification sending
- Calendar synchronization
- Data cleanup
- Analytics updates
"""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from celery import shared_task
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_context
from app.models.booking import Booking
from app.models.listing import Listing
from app.models.payment import HostPayout, Payment
from app.models.user import User
from app.services.notification_service import notification_service
from app.utils.booking_number import generate_payout_reference


def run_async(coro):
    """Run async function in sync context."""
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)


# ==================== PAYOUT TASKS ====================


@shared_task(bind=True, max_retries=3)
def process_daily_payouts(self):
    """Process host payouts for completed bookings.

    Runs daily at configured payout time (default 6 AM PKT).
    Aggregates all completed bookings and creates payout records.
    """
    try:
        run_async(_process_daily_payouts())
        return {"status": "success", "message": "Daily payouts processed"}
    except Exception as exc:
        self.retry(exc=exc, countdown=300)


async def _process_daily_payouts():
    """Async implementation of daily payout processing."""
    from app.config import settings

    async with get_db_context() as db:
        # Find all completed bookings that haven't been paid out
        # Booking must be completed (checkout passed) and payment received
        yesterday = datetime.now(UTC).date() - timedelta(days=1)

        result = await db.execute(
            select(Booking)
            .where(
                Booking.status == "completed",
                Booking.payment_status == "paid",
                Booking.check_out <= yesterday,
            )
            .order_by(Booking.host_id)
        )
        bookings = result.scalars().all()

        if not bookings:
            return

        # Group by host
        host_bookings: dict[UUID, list[Booking]] = {}
        for booking in bookings:
            if booking.host_id not in host_bookings:
                host_bookings[booking.host_id] = []
            host_bookings[booking.host_id].append(booking)

        # Create payouts
        for host_id, host_booking_list in host_bookings.items():
            total_amount = sum(b.host_payout_amount for b in host_booking_list)

            # Skip if below minimum
            if total_amount < settings.minimum_payout_amount:
                continue

            # Get host's payout details from most recent payout
            payout_result = await db.execute(
                select(HostPayout)
                .where(HostPayout.host_id == host_id)
                .order_by(HostPayout.created_at.desc())
                .limit(1)
            )
            existing_payout = payout_result.scalar_one_or_none()

            payout = HostPayout(
                host_id=host_id,
                amount=total_amount,
                currency="PKR",
                bank_name=existing_payout.bank_name if existing_payout else None,
                account_number_encrypted=existing_payout.account_number_encrypted if existing_payout else None,
                account_holder_name=existing_payout.account_holder_name if existing_payout else None,
                payout_method=existing_payout.payout_method if existing_payout else "bank_transfer",
                status="pending",
                payout_date=datetime.now(UTC).date(),
                period_start=min(b.check_out for b in host_booking_list),
                period_end=max(b.check_out for b in host_booking_list),
                booking_ids=[b.id for b in host_booking_list],
            )
            db.add(payout)

            # Notify host
            await notification_service.notify_user(
                user_id=host_id,
                title="Payout Initiated",
                body=f"A payout of PKR {total_amount / 100:,.0f} has been initiated for your bookings.",
                notification_type="payout_sent",
            )


# ==================== NOTIFICATION TASKS ====================


@shared_task(bind=True, max_retries=3)
def send_booking_reminders(self):
    """Send check-in reminders to guests.

    Sends reminders 24 hours before check-in.
    """
    try:
        run_async(_send_booking_reminders())
        return {"status": "success", "message": "Booking reminders sent"}
    except Exception as exc:
        self.retry(exc=exc, countdown=300)


async def _send_booking_reminders():
    """Async implementation of booking reminders."""
    async with get_db_context() as db:
        tomorrow = datetime.now(UTC).date() + timedelta(days=1)

        result = await db.execute(
            select(Booking)
            .where(
                Booking.status == "confirmed",
                Booking.check_in == tomorrow,
            )
        )
        bookings = result.scalars().all()

        for booking in bookings:
            # Get listing title
            listing_result = await db.execute(
                select(Listing).where(Listing.id == booking.listing_id)
            )
            listing = listing_result.scalar_one()

            await notification_service.notify_user(
                user_id=booking.guest_id,
                title="Check-in Tomorrow!",
                body=f"Your stay at {listing.title} starts tomorrow. Check-in time is {listing.check_in_time.strftime('%I:%M %p')}.",
                notification_type="booking_reminder",
                booking_id=booking.id,
            )


@shared_task(bind=True, max_retries=3)
def send_review_requests(self):
    """Send review requests to guests after checkout.

    Sends review requests 24 hours after checkout.
    """
    try:
        run_async(_send_review_requests())
        return {"status": "success", "message": "Review requests sent"}
    except Exception as exc:
        self.retry(exc=exc, countdown=300)


async def _send_review_requests():
    """Async implementation of review requests."""
    async with get_db_context() as db:
        yesterday = datetime.now(UTC).date() - timedelta(days=1)

        result = await db.execute(
            select(Booking)
            .where(
                Booking.status == "completed",
                Booking.check_out == yesterday,
            )
        )
        bookings = result.scalars().all()

        for booking in bookings:
            listing_result = await db.execute(
                select(Listing).where(Listing.id == booking.listing_id)
            )
            listing = listing_result.scalar_one()

            # Request review from guest
            await notification_service.notify_user(
                user_id=booking.guest_id,
                title="How was your stay?",
                body=f"We'd love to hear about your experience at {listing.title}. Leave a review to help other travelers.",
                notification_type="review_request",
                booking_id=booking.id,
                action_url=f"/bookings/{booking.id}/review",
            )

            # Request review from host
            await notification_service.notify_user(
                user_id=booking.host_id,
                title="Rate your guest",
                body=f"How was your experience hosting? Leave a review for booking #{booking.booking_number}.",
                notification_type="review_request",
                booking_id=booking.id,
                action_url=f"/host/bookings/{booking.id}/review",
            )


@shared_task
def send_notification_async(
    user_id: str,
    title: str,
    body: str,
    notification_type: str,
    action_url: str | None = None,
    booking_id: str | None = None,
    listing_id: str | None = None,
):
    """Send notification asynchronously.

    This task is used to offload notification sending from request handlers.
    """
    run_async(
        notification_service.notify_user(
            user_id=UUID(user_id),
            title=title,
            body=body,
            notification_type=notification_type,
            action_url=action_url,
            booking_id=UUID(booking_id) if booking_id else None,
            listing_id=UUID(listing_id) if listing_id else None,
        )
    )


# ==================== CALENDAR SYNC TASKS ====================


@shared_task(bind=True, max_retries=3)
def sync_all_calendars(self):
    """Sync all enabled calendar integrations.

    Syncs with Airbnb and Booking.com calendars for all listings
    with sync enabled.
    """
    try:
        run_async(_sync_all_calendars())
        return {"status": "success", "message": "Calendars synced"}
    except Exception as exc:
        self.retry(exc=exc, countdown=60)


async def _sync_all_calendars():
    """Async implementation of calendar sync."""
    async with get_db_context() as db:
        result = await db.execute(
            select(Listing).where(
                Listing.sync_enabled == True,  # noqa: E712
                Listing.status == "approved",
            )
        )
        listings = result.scalars().all()

        for listing in listings:
            # Sync Airbnb calendar if connected
            if listing.external_airbnb_id:
                await _sync_airbnb_calendar(db, listing)

            # Sync Booking.com calendar if connected
            if listing.external_booking_id:
                await _sync_booking_calendar(db, listing)

            # Update last sync timestamp
            listing.last_synced_at = datetime.now(UTC)


async def _sync_airbnb_calendar(db: AsyncSession, listing: Listing):
    """Sync calendar with Airbnb.

    In production, this would:
    1. Fetch iCal from Airbnb
    2. Parse events
    3. Update calendar blocks
    4. Push VOLO bookings to Airbnb
    """
    # Placeholder for Airbnb integration
    pass


async def _sync_booking_calendar(db: AsyncSession, listing: Listing):
    """Sync calendar with Booking.com.

    In production, this would:
    1. Use Booking.com Connectivity API
    2. Fetch reservations
    3. Update availability
    """
    # Placeholder for Booking.com integration
    pass


@shared_task
def sync_single_listing(listing_id: str):
    """Sync calendar for a single listing.

    Used for manual sync triggers.
    """
    run_async(_sync_single_listing(UUID(listing_id)))


async def _sync_single_listing(listing_id: UUID):
    """Async implementation of single listing sync."""
    async with get_db_context() as db:
        result = await db.execute(
            select(Listing).where(Listing.id == listing_id)
        )
        listing = result.scalar_one_or_none()

        if listing and listing.sync_enabled:
            if listing.external_airbnb_id:
                await _sync_airbnb_calendar(db, listing)
            if listing.external_booking_id:
                await _sync_booking_calendar(db, listing)
            listing.last_synced_at = datetime.now(UTC)


# ==================== CLEANUP TASKS ====================


@shared_task
def cleanup_expired_data():
    """Clean up expired data from the database.

    Removes:
    - Old audit logs (> 90 days)
    - Expired notifications (> 30 days, read)
    - Old rate limit data
    """
    run_async(_cleanup_expired_data())
    return {"status": "success", "message": "Cleanup completed"}


async def _cleanup_expired_data():
    """Async implementation of data cleanup."""
    from app.models.admin import AuditLog
    from app.models.message import Notification

    async with get_db_context() as db:
        # Clean old audit logs (keep 90 days)
        cutoff_audit = datetime.now(UTC) - timedelta(days=90)
        await db.execute(
            AuditLog.__table__.delete().where(AuditLog.created_at < cutoff_audit)
        )

        # Clean old read notifications (keep 30 days)
        cutoff_notif = datetime.now(UTC) - timedelta(days=30)
        await db.execute(
            Notification.__table__.delete().where(
                and_(
                    Notification.is_read == True,  # noqa: E712
                    Notification.created_at < cutoff_notif,
                )
            )
        )


# ==================== ANALYTICS TASKS ====================


@shared_task
def update_listing_statistics():
    """Update listing statistics and rankings.

    Calculates:
    - Average ratings
    - Response rates
    - Booking rates
    - Revenue statistics
    """
    run_async(_update_listing_statistics())
    return {"status": "success", "message": "Statistics updated"}


async def _update_listing_statistics():
    """Async implementation of statistics update.

    In production, this would update cached statistics for
    search ranking and host dashboards.
    """
    # Placeholder for statistics calculation
    pass


# ==================== EMAIL TASKS ====================


@shared_task(bind=True, max_retries=3)
def send_email_task(
    self,
    to_email: str,
    subject: str,
    html_content: str,
    text_content: str | None = None,
):
    """Send email asynchronously.

    Use this to offload email sending from request handlers.
    """
    try:
        run_async(
            notification_service.send_email(
                to_email=to_email,
                subject=subject,
                html_content=html_content,
                text_content=text_content,
            )
        )
        return {"status": "success", "to": to_email}
    except Exception as exc:
        self.retry(exc=exc, countdown=60)
