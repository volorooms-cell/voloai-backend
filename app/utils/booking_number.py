"""Booking number and slug generation utilities."""

import random
import string
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def generate_booking_number(db: AsyncSession) -> str:
    """Generate a unique booking number in format VOLO-XXXXXX.

    Args:
        db: Database session for uniqueness check

    Returns:
        str: Unique booking number like 'VOLO-A3B7K9'
    """
    from app.models.booking import Booking

    while True:
        # Generate 6 alphanumeric characters (uppercase + digits)
        chars = string.ascii_uppercase + string.digits
        random_part = "".join(random.choices(chars, k=6))
        booking_number = f"VOLO-{random_part}"

        # Check uniqueness
        result = await db.execute(
            select(Booking).where(Booking.booking_number == booking_number)
        )
        if not result.scalar_one_or_none():
            return booking_number


async def generate_slug(db: AsyncSession, prefix: str = "") -> str:
    """Generate a unique slug for direct booking links.

    Args:
        db: Database session for uniqueness check
        prefix: Optional prefix (e.g., city name)

    Returns:
        str: Unique slug like 'cozy-karachi-a7b3' or 'lahore-view-k9m2'
    """
    from app.models.listing import Listing

    # Adjectives for property descriptions
    adjectives = [
        "cozy", "sunny", "modern", "charming", "peaceful",
        "elegant", "lovely", "bright", "spacious", "beautiful",
    ]

    while True:
        # Generate slug: adjective + optional prefix + 4 random chars
        adj = random.choice(adjectives)
        random_suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))

        if prefix:
            slug = f"{adj}-{prefix.lower()}-{random_suffix}"
        else:
            slug = f"{adj}-stay-{random_suffix}"

        # Ensure slug is URL-safe
        slug = "".join(c if c.isalnum() or c == "-" else "-" for c in slug)
        slug = "-".join(part for part in slug.split("-") if part)  # Remove double dashes

        # Check uniqueness
        result = await db.execute(
            select(Listing).where(Listing.direct_booking_slug == slug)
        )
        if not result.scalar_one_or_none():
            return slug


def generate_receipt_number() -> str:
    """Generate a receipt number for payments.

    Returns:
        str: Receipt number like 'RCP-20240115-A3B7'
    """
    date_part = datetime.now().strftime("%Y%m%d")
    random_part = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"RCP-{date_part}-{random_part}"


def generate_payout_reference() -> str:
    """Generate a payout reference number.

    Returns:
        str: Payout reference like 'PAY-20240115-K9M2'
    """
    date_part = datetime.now().strftime("%Y%m%d")
    random_part = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"PAY-{date_part}-{random_part}"
