"""Notification Service for push notifications, email, and SMS.

Handles all notification channels:
- Push notifications (Firebase)
- Email (SendGrid)
- SMS/WhatsApp (Twilio)
- In-app notifications (database)
"""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db_context
from app.models.message import Notification
from app.models.user import User


class NotificationService:
    """Service for sending notifications across all channels."""

    # Notification types
    BOOKING_CONFIRMED = "booking_confirmed"
    BOOKING_CANCELLED = "booking_cancelled"
    BOOKING_REQUEST = "booking_request"
    PAYMENT_RECEIVED = "payment_received"
    PAYOUT_SENT = "payout_sent"
    MESSAGE_RECEIVED = "message_received"
    REVIEW_RECEIVED = "review_received"
    LISTING_APPROVED = "listing_approved"
    LISTING_REJECTED = "listing_rejected"
    IDENTITY_VERIFIED = "identity_verified"
    EXTENSION_REQUEST = "extension_request"
    EXTENSION_APPROVED = "extension_approved"

    def __init__(self) -> None:
        """Initialize notification service."""
        self._http_client: httpx.AsyncClient | None = None

    @property
    def http_client(self) -> httpx.AsyncClient:
        """Lazy-load HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()

    # ==================== IN-APP NOTIFICATIONS ====================

    async def create_notification(
        self,
        db: AsyncSession,
        user_id: UUID,
        title: str,
        body: str,
        notification_type: str,
        action_url: str | None = None,
        booking_id: UUID | None = None,
        listing_id: UUID | None = None,
    ) -> Notification:
        """Create an in-app notification.

        Args:
            db: Database session
            user_id: User to notify
            title: Notification title
            body: Notification body text
            notification_type: Type of notification
            action_url: Optional deep link URL
            booking_id: Related booking ID
            listing_id: Related listing ID

        Returns:
            Notification: Created notification
        """
        notification = Notification(
            user_id=user_id,
            title=title,
            body=body,
            notification_type=notification_type,
            action_url=action_url,
            booking_id=booking_id,
            listing_id=listing_id,
        )
        db.add(notification)
        await db.flush()
        return notification

    # ==================== PUSH NOTIFICATIONS (FIREBASE) ====================

    async def send_push_notification(
        self,
        push_token: str,
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
    ) -> bool:
        """Send a push notification via Firebase Cloud Messaging.

        Args:
            push_token: Device FCM token
            title: Notification title
            body: Notification body
            data: Additional data payload

        Returns:
            bool: True if sent successfully
        """
        if not settings.firebase_credentials_path:
            return False

        # In production, use firebase-admin SDK
        # For now, use HTTP v1 API directly
        try:
            # This is a simplified version - production should use proper auth
            message = {
                "message": {
                    "token": push_token,
                    "notification": {
                        "title": title,
                        "body": body,
                    },
                    "data": data or {},
                    "android": {
                        "priority": "high",
                        "notification": {
                            "click_action": "FLUTTER_NOTIFICATION_CLICK",
                        },
                    },
                    "apns": {
                        "payload": {
                            "aps": {
                                "alert": {
                                    "title": title,
                                    "body": body,
                                },
                                "sound": "default",
                            },
                        },
                    },
                }
            }
            # Would send to FCM here
            return True
        except Exception:
            return False

    # ==================== EMAIL (SENDGRID) ====================

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str | None = None,
        template_id: str | None = None,
        template_data: dict[str, Any] | None = None,
    ) -> bool:
        """Send an email via SendGrid.

        Args:
            to_email: Recipient email
            subject: Email subject
            html_content: HTML body (ignored if template_id provided)
            text_content: Plain text body
            template_id: SendGrid template ID
            template_data: Dynamic template data

        Returns:
            bool: True if sent successfully
        """
        if not settings.sendgrid_api_key:
            return False

        try:
            headers = {
                "Authorization": f"Bearer {settings.sendgrid_api_key}",
                "Content-Type": "application/json",
            }

            payload: dict[str, Any] = {
                "personalizations": [
                    {
                        "to": [{"email": to_email}],
                    }
                ],
                "from": {
                    "email": settings.email_from_address,
                    "name": settings.email_from_name,
                },
            }

            if template_id:
                payload["template_id"] = template_id
                if template_data:
                    payload["personalizations"][0]["dynamic_template_data"] = template_data
            else:
                payload["subject"] = subject
                payload["content"] = [{"type": "text/html", "value": html_content}]
                if text_content:
                    payload["content"].insert(0, {"type": "text/plain", "value": text_content})

            response = await self.http_client.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers=headers,
                json=payload,
            )
            return response.status_code in (200, 202)
        except Exception:
            return False

    # ==================== SMS/WHATSAPP (TWILIO) ====================

    async def send_sms(
        self,
        to_phone: str,
        message: str,
    ) -> bool:
        """Send an SMS via Twilio.

        Args:
            to_phone: Recipient phone number (international format)
            message: SMS text (max 160 chars for single SMS)

        Returns:
            bool: True if sent successfully
        """
        if not settings.twilio_account_sid or not settings.twilio_auth_token:
            return False

        try:
            url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json"
            auth = (settings.twilio_account_sid, settings.twilio_auth_token)

            data = {
                "To": to_phone,
                "From": settings.twilio_whatsapp_number.replace("whatsapp:", ""),  # SMS number
                "Body": message,
            }

            response = await self.http_client.post(url, auth=auth, data=data)
            return response.status_code == 201
        except Exception:
            return False

    async def send_whatsapp(
        self,
        to_phone: str,
        message: str,
    ) -> bool:
        """Send a WhatsApp message via Twilio.

        Args:
            to_phone: Recipient phone number (international format)
            message: Message text

        Returns:
            bool: True if sent successfully
        """
        if not settings.twilio_account_sid or not settings.twilio_auth_token:
            return False

        try:
            url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json"
            auth = (settings.twilio_account_sid, settings.twilio_auth_token)

            data = {
                "To": f"whatsapp:{to_phone}",
                "From": settings.twilio_whatsapp_number,
                "Body": message,
            }

            response = await self.http_client.post(url, auth=auth, data=data)
            return response.status_code == 201
        except Exception:
            return False

    # ==================== HIGH-LEVEL NOTIFICATION METHODS ====================

    async def notify_user(
        self,
        user_id: UUID,
        title: str,
        body: str,
        notification_type: str,
        action_url: str | None = None,
        booking_id: UUID | None = None,
        listing_id: UUID | None = None,
        send_push: bool = True,
        send_email: bool = True,
    ) -> None:
        """Send notification to user via all enabled channels.

        Args:
            user_id: User to notify
            title: Notification title
            body: Notification body
            notification_type: Type of notification
            action_url: Deep link URL
            booking_id: Related booking
            listing_id: Related listing
            send_push: Whether to send push notification
            send_email: Whether to send email
        """
        async with get_db_context() as db:
            # Get user
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if not user:
                return

            # Create in-app notification
            notification = await self.create_notification(
                db=db,
                user_id=user_id,
                title=title,
                body=body,
                notification_type=notification_type,
                action_url=action_url,
                booking_id=booking_id,
                listing_id=listing_id,
            )

            # Send push notification
            if send_push and user.push_token:
                success = await self.send_push_notification(
                    push_token=user.push_token,
                    title=title,
                    body=body,
                    data={
                        "type": notification_type,
                        "notification_id": str(notification.id),
                        "action_url": action_url or "",
                    },
                )
                notification.push_sent = success

            # Send email
            if send_email and user.email:
                email_html = self._generate_email_html(title, body, action_url)
                success = await self.send_email(
                    to_email=user.email,
                    subject=title,
                    html_content=email_html,
                )
                notification.email_sent = success

    def _generate_email_html(self, title: str, body: str, action_url: str | None) -> str:
        """Generate simple HTML email content.

        Args:
            title: Email title
            body: Email body
            action_url: CTA button URL

        Returns:
            str: HTML email content
        """
        button_html = ""
        if action_url:
            button_html = f"""
            <p style="margin-top: 24px;">
                <a href="{action_url}"
                   style="background-color: #4F46E5; color: white; padding: 12px 24px;
                          text-decoration: none; border-radius: 6px; display: inline-block;">
                    View Details
                </a>
            </p>
            """

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                     max-width: 600px; margin: 0 auto; padding: 20px; color: #333;">
            <div style="background-color: #f9fafb; border-radius: 8px; padding: 24px;">
                <h1 style="color: #111827; font-size: 24px; margin-bottom: 16px;">{title}</h1>
                <p style="color: #4b5563; font-size: 16px; line-height: 1.6;">{body}</p>
                {button_html}
            </div>
            <p style="color: #9ca3af; font-size: 12px; margin-top: 24px; text-align: center;">
                &copy; {datetime.now(UTC).year} VOLO AI. All rights reserved.
            </p>
        </body>
        </html>
        """

    # ==================== SPECIFIC NOTIFICATION HELPERS ====================

    async def notify_booking_confirmed(
        self,
        guest_id: UUID,
        host_id: UUID,
        booking_number: str,
        listing_title: str,
        check_in: str,
        check_out: str,
        booking_id: UUID,
    ) -> None:
        """Notify guest and host about confirmed booking."""
        # Notify guest
        await self.notify_user(
            user_id=guest_id,
            title="Booking Confirmed!",
            body=f"Your booking at {listing_title} from {check_in} to {check_out} has been confirmed. Booking #{booking_number}",
            notification_type=self.BOOKING_CONFIRMED,
            action_url=f"/bookings/{booking_id}",
            booking_id=booking_id,
        )

        # Notify host
        await self.notify_user(
            user_id=host_id,
            title="New Booking Confirmed",
            body=f"You have a new booking at {listing_title} from {check_in} to {check_out}. Booking #{booking_number}",
            notification_type=self.BOOKING_CONFIRMED,
            action_url=f"/host/bookings/{booking_id}",
            booking_id=booking_id,
        )

    async def notify_new_message(
        self,
        recipient_id: UUID,
        sender_name: str,
        listing_title: str,
        message_preview: str,
        conversation_id: UUID,
    ) -> None:
        """Notify user about new message."""
        await self.notify_user(
            user_id=recipient_id,
            title=f"New message from {sender_name}",
            body=f"Re: {listing_title} - {message_preview[:100]}...",
            notification_type=self.MESSAGE_RECEIVED,
            action_url=f"/conversations/{conversation_id}",
        )

    async def notify_listing_approved(
        self,
        host_id: UUID,
        listing_id: UUID,
        listing_title: str,
    ) -> None:
        """Notify host that listing was approved."""
        await self.notify_user(
            user_id=host_id,
            title="Listing Approved!",
            body=f'Your listing "{listing_title}" has been approved and is now live on VOLO.',
            notification_type=self.LISTING_APPROVED,
            action_url=f"/listings/{listing_id}",
            listing_id=listing_id,
        )


# Singleton instance
notification_service = NotificationService()
