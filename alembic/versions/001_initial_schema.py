"""Initial database schema.

Revision ID: 001_initial
Revises: None
Create Date: 2024-01-19

Creates all initial tables for the VOLO AI platform:
- Users and authentication
- Listings and amenities
- Bookings and calendar
- Payments and payouts
- Messages and notifications
- Reviews
- Admin (audit logs, disputes)
"""

from typing import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers
revision: str = "001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create all database tables."""

    # ==================== USERS ====================
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("phone", sa.String(20), unique=True, index=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, default="guest"),
        sa.Column("first_name", sa.String(100)),
        sa.Column("last_name", sa.String(100)),
        sa.Column("profile_photo_url", sa.Text),
        sa.Column("bio", sa.Text),
        sa.Column("is_verified", sa.Boolean, default=False),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("is_email_verified", sa.Boolean, default=False),
        sa.Column("is_phone_verified", sa.Boolean, default=False),
        sa.Column("preferred_language", sa.String(10), default="en"),
        sa.Column("preferred_currency", sa.String(3), default="PKR"),
        sa.Column("loyalty_tier", sa.String(20), default="bronze"),
        sa.Column("total_stays", sa.Integer, default=0),
        sa.Column("total_nights", sa.Integer, default=0),
        sa.Column("push_token", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "user_identity",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_type", sa.String(20), nullable=False),
        sa.Column("document_number_encrypted", sa.LargeBinary, nullable=False),
        sa.Column("document_front_url", sa.Text, nullable=False),
        sa.Column("document_back_url", sa.Text),
        sa.Column("face_scan_url", sa.Text, nullable=False),
        sa.Column("verification_status", sa.String(20), default="pending"),
        sa.Column("rejection_reason", sa.Text),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ==================== AMENITIES ====================
    op.create_table(
        "amenities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), unique=True, nullable=False),
        sa.Column("category", sa.String(50)),
        sa.Column("icon", sa.String(50)),
    )

    # ==================== LISTINGS ====================
    op.create_table(
        "listings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("host_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("listing_type", sa.String(30), nullable=False),
        sa.Column("property_type", sa.String(50)),
        sa.Column("address_line1", sa.String(255)),
        sa.Column("address_line2", sa.String(255)),
        sa.Column("city", sa.String(100), nullable=False, index=True),
        sa.Column("state_province", sa.String(100)),
        sa.Column("postal_code", sa.String(20)),
        sa.Column("country", sa.String(2), default="PK"),
        sa.Column("latitude", sa.Numeric(10, 8)),
        sa.Column("longitude", sa.Numeric(11, 8)),
        sa.Column("max_guests", sa.Integer, nullable=False, default=1),
        sa.Column("bedrooms", sa.Integer, default=0),
        sa.Column("beds", sa.Integer, default=0),
        sa.Column("bathrooms", sa.Numeric(3, 1), default=1),
        sa.Column("base_price_per_night", sa.Integer, nullable=False),
        sa.Column("cleaning_fee", sa.Integer, default=0),
        sa.Column("service_fee_percent", sa.Numeric(5, 2), default=5.00),
        sa.Column("currency", sa.String(3), default="PKR"),
        sa.Column("cancellation_policy", sa.String(30), default="flexible"),
        sa.Column("check_in_time", sa.Time, default="14:00"),
        sa.Column("check_out_time", sa.Time, default="11:00"),
        sa.Column("min_nights", sa.Integer, default=1),
        sa.Column("max_nights", sa.Integer, default=365),
        sa.Column("instant_booking", sa.Boolean, default=False),
        sa.Column("status", sa.String(20), default="draft", index=True),
        sa.Column("approval_notes", sa.Text),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("direct_booking_slug", sa.String(50), unique=True),
        sa.Column("whatsapp_ai_enabled", sa.Boolean, default=False),
        sa.Column("whatsapp_ai_greeting", sa.Text),
        sa.Column("external_airbnb_id", sa.String(100)),
        sa.Column("external_booking_id", sa.String(100)),
        sa.Column("sync_enabled", sa.Boolean, default=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    op.create_table(
        "listing_photos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("listings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("caption", sa.String(255)),
        sa.Column("sort_order", sa.Integer, default=0),
        sa.Column("is_cover", sa.Boolean, default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "listing_amenities",
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("listings.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("amenity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("amenities.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_table(
        "house_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("listings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_type", sa.String(50)),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("is_allowed", sa.Boolean, default=False),
    )

    op.create_table(
        "pricing_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("listings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_type", sa.String(30), nullable=False),
        sa.Column("discount_percent", sa.Numeric(5, 2)),
        sa.Column("price_override", sa.Integer),
        sa.Column("min_nights", sa.Integer),
        sa.Column("start_date", sa.Date),
        sa.Column("end_date", sa.Date),
        sa.Column("days_of_week", postgresql.ARRAY(sa.Integer)),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "cohost_permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("host_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cohost_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("listings.id", ondelete="CASCADE")),
        sa.Column("can_manage_bookings", sa.Boolean, default=True),
        sa.Column("can_manage_calendar", sa.Boolean, default=True),
        sa.Column("can_manage_pricing", sa.Boolean, default=False),
        sa.Column("can_message_guests", sa.Boolean, default=True),
        sa.Column("can_view_payouts", sa.Boolean, default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("host_id", "cohost_id", "listing_id", name="unique_cohost_permission"),
    )

    # ==================== BOOKINGS ====================
    op.create_table(
        "calendar_blocks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("listings.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("start_date", sa.Date, nullable=False, index=True),
        sa.Column("end_date", sa.Date, nullable=False, index=True),
        sa.Column("block_type", sa.String(20), default="manual"),
        sa.Column("external_booking_id", sa.String(100)),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "bookings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("booking_number", sa.String(20), unique=True, nullable=False, index=True),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("listings.id"), nullable=False, index=True),
        sa.Column("guest_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("host_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("commission_rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("check_in", sa.Date, nullable=False, index=True),
        sa.Column("check_out", sa.Date, nullable=False, index=True),
        sa.Column("adults", sa.Integer, default=1),
        sa.Column("children", sa.Integer, default=0),
        sa.Column("infants", sa.Integer, default=0),
        sa.Column("nightly_rate", sa.Integer, nullable=False),
        sa.Column("subtotal", sa.Integer, nullable=False),
        sa.Column("cleaning_fee", sa.Integer, default=0),
        sa.Column("service_fee", sa.Integer, default=0),
        sa.Column("taxes", sa.Integer, default=0),
        sa.Column("total_price", sa.Integer, nullable=False),
        sa.Column("currency", sa.String(3), default="PKR"),
        sa.Column("commission_amount", sa.Integer, nullable=False),
        sa.Column("host_payout_amount", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), default="pending", index=True),
        sa.Column("payment_status", sa.String(20), default="pending"),
        sa.Column("cancelled_by", sa.String(10)),
        sa.Column("cancellation_reason", sa.Text),
        sa.Column("refund_amount", sa.Integer, default=0),
        sa.Column("special_requests", sa.Text),
        sa.Column("booked_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    op.create_table(
        "booking_extensions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bookings.id"), nullable=False),
        sa.Column("original_check_out", sa.Date, nullable=False),
        sa.Column("new_check_out", sa.Date, nullable=False),
        sa.Column("additional_nights", sa.Integer, nullable=False),
        sa.Column("additional_amount", sa.Integer, nullable=False),
        sa.Column("commission_amount", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), default="pending"),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
    )

    # ==================== PAYMENTS ====================
    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bookings.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("amount", sa.Integer, nullable=False),
        sa.Column("currency", sa.String(3), default="PKR"),
        sa.Column("payment_method", sa.String(30), nullable=False),
        sa.Column("gateway", sa.String(30)),
        sa.Column("gateway_transaction_id", sa.String(100)),
        sa.Column("gateway_response", postgresql.JSONB),
        sa.Column("status", sa.String(20), default="pending"),
        sa.Column("initiated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "host_payouts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("host_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("amount", sa.Integer, nullable=False),
        sa.Column("currency", sa.String(3), default="PKR"),
        sa.Column("bank_name", sa.String(100)),
        sa.Column("account_number_encrypted", sa.LargeBinary),
        sa.Column("account_holder_name", sa.String(200)),
        sa.Column("payout_method", sa.String(30)),
        sa.Column("status", sa.String(20), default="pending"),
        sa.Column("gateway_transaction_id", sa.String(100)),
        sa.Column("gateway_response", postgresql.JSONB),
        sa.Column("payout_date", sa.Date, nullable=False),
        sa.Column("period_start", sa.Date),
        sa.Column("period_end", sa.Date),
        sa.Column("booking_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True))),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "refunds",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bookings.id"), nullable=False),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("payments.id"), nullable=False),
        sa.Column("amount", sa.Integer, nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column("status", sa.String(20), default="pending"),
        sa.Column("deducted_from_payout_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("host_payouts.id")),
        sa.Column("processed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("gateway_refund_id", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ==================== MESSAGES ====================
    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bookings.id"), unique=True),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("listings.id"), nullable=False),
        sa.Column("guest_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("host_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("is_archived_by_guest", sa.Boolean, default=False),
        sa.Column("is_archived_by_host", sa.Boolean, default=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("sender_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("message_type", sa.String(20), default="text"),
        sa.Column("image_url", sa.Text),
        sa.Column("is_read", sa.Boolean, default=False),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
    )

    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("notification_type", sa.String(50), nullable=False),
        sa.Column("action_url", sa.Text),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bookings.id")),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("listings.id")),
        sa.Column("is_read", sa.Boolean, default=False),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("push_sent", sa.Boolean, default=False),
        sa.Column("whatsapp_sent", sa.Boolean, default=False),
        sa.Column("email_sent", sa.Boolean, default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ==================== REVIEWS ====================
    op.create_table(
        "reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bookings.id"), nullable=False),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("listings.id"), nullable=False, index=True),
        sa.Column("reviewer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("review_type", sa.String(20), nullable=False),
        sa.Column("overall_rating", sa.Integer),
        sa.Column("cleanliness_rating", sa.Integer),
        sa.Column("accuracy_rating", sa.Integer),
        sa.Column("communication_rating", sa.Integer),
        sa.Column("location_rating", sa.Integer),
        sa.Column("value_rating", sa.Integer),
        sa.Column("checkin_rating", sa.Integer),
        sa.Column("public_review", sa.Text),
        sa.Column("private_feedback", sa.Text),
        sa.Column("status", sa.String(20), default="published"),
        sa.Column("moderation_notes", sa.Text),
        sa.Column("moderated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # ==================== ADMIN ====================
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), index=True),
        sa.Column("action", sa.String(100), nullable=False, index=True),
        sa.Column("resource_type", sa.String(50), nullable=False, index=True),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True)),
        sa.Column("old_values", postgresql.JSONB),
        sa.Column("new_values", postgresql.JSONB),
        sa.Column("ip_address", postgresql.INET),
        sa.Column("user_agent", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
    )

    op.create_table(
        "disputes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bookings.id"), nullable=False),
        sa.Column("raised_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("against_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("evidence_urls", postgresql.ARRAY(sa.Text)),
        sa.Column("status", sa.String(20), default="open"),
        sa.Column("resolution", sa.Text),
        sa.Column("refund_granted", sa.Integer, default=0),
        sa.Column("assigned_to", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    """Drop all database tables in reverse order."""
    op.drop_table("disputes")
    op.drop_table("audit_logs")
    op.drop_table("reviews")
    op.drop_table("notifications")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("refunds")
    op.drop_table("host_payouts")
    op.drop_table("payments")
    op.drop_table("booking_extensions")
    op.drop_table("bookings")
    op.drop_table("calendar_blocks")
    op.drop_table("cohost_permissions")
    op.drop_table("pricing_rules")
    op.drop_table("house_rules")
    op.drop_table("listing_amenities")
    op.drop_table("listing_photos")
    op.drop_table("listings")
    op.drop_table("amenities")
    op.drop_table("user_identity")
    op.drop_table("users")
