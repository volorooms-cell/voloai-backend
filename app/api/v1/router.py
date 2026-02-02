"""Main API router that includes all endpoint routers."""

from fastapi import APIRouter

from app.api.v1 import (
    admin,
    auth,
    bookings,
    channels,
    disputes,
    internal,
    listings,
    messages,
    notifications,
    payments,
    payouts,
    reports,
    reviews,
    search,
    users,
    webhooks,
)

api_router = APIRouter()

# Authentication
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])

# Users
api_router.include_router(users.router, prefix="/users", tags=["Users"])

# Listings
api_router.include_router(listings.router, prefix="/listings", tags=["Listings"])

# Search
api_router.include_router(search.router, prefix="/search", tags=["Search"])

# Bookings
api_router.include_router(bookings.router, prefix="/bookings", tags=["Bookings"])

# Payments
api_router.include_router(payments.router, prefix="/payments", tags=["Payments"])

# Payouts
api_router.include_router(payouts.router, prefix="/payouts", tags=["Payouts"])

# Messages
api_router.include_router(messages.router, prefix="/conversations", tags=["Messages"])

# Notifications
api_router.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])

# Reviews
api_router.include_router(reviews.router, prefix="/reviews", tags=["Reviews"])

# Channel Sync
api_router.include_router(channels.router, prefix="/channels", tags=["Channels"])

# Admin
api_router.include_router(admin.router, prefix="/admin", tags=["Admin"])

# Webhooks
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])

# Reports
api_router.include_router(reports.router, prefix="/reports", tags=["Reports"])

# Disputes
api_router.include_router(disputes.router, prefix="/disputes", tags=["Disputes"])

# Internal
api_router.include_router(internal.router, prefix="/internal", tags=["Internal"])
