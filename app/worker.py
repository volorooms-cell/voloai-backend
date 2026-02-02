"""Celery worker configuration and task definitions.

This module sets up Celery for background task processing including:
- Scheduled payouts
- Email sending
- Notification dispatch
- Channel synchronization
- Data cleanup
"""

from celery import Celery
from celery.schedules import crontab

from app.config import settings

# Create Celery app
celery_app = Celery(
    "volo_tasks",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks"],
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Karachi",
    enable_utc=True,

    # Task execution settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=300,  # 5 minutes max
    task_soft_time_limit=240,  # Soft limit at 4 minutes

    # Worker settings
    worker_prefetch_multiplier=1,
    worker_concurrency=4,

    # Result backend settings
    result_expires=3600,  # Results expire after 1 hour

    # Retry settings
    task_default_retry_delay=60,  # 1 minute
    task_max_retries=3,

    # Beat schedule for periodic tasks
    beat_schedule={
        # Process payouts daily at 6 AM PKT
        "process-daily-payouts": {
            "task": "app.tasks.process_daily_payouts",
            "schedule": crontab(hour=settings.payout_time_hour, minute=0),
        },
        # Sync calendars every 15 minutes
        "sync-external-calendars": {
            "task": "app.tasks.sync_all_calendars",
            "schedule": crontab(minute="*/15"),
        },
        # Send booking reminders daily at 9 AM
        "send-booking-reminders": {
            "task": "app.tasks.send_booking_reminders",
            "schedule": crontab(hour=9, minute=0),
        },
        # Clean up expired sessions daily at 3 AM
        "cleanup-expired-data": {
            "task": "app.tasks.cleanup_expired_data",
            "schedule": crontab(hour=3, minute=0),
        },
        # Update listing statistics hourly
        "update-listing-stats": {
            "task": "app.tasks.update_listing_statistics",
            "schedule": crontab(minute=0),
        },
        # Send review requests 24 hours after checkout
        "send-review-requests": {
            "task": "app.tasks.send_review_requests",
            "schedule": crontab(hour=10, minute=0),
        },
    },
)


if __name__ == "__main__":
    celery_app.start()
