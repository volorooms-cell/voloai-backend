"""Cancellation policy domain logic.

Policies:
- flexible: Full refund up to 24h before check-in, 50% after
- moderate: Full refund up to 5 days before, 50% up to 24h, 0% after
- strict: 50% refund up to 7 days before, 0% after
"""

from datetime import date, timedelta
from decimal import Decimal
from enum import Enum


class CancellationPolicy(str, Enum):
    """Cancellation policy types."""

    FLEXIBLE = "flexible"
    MODERATE = "moderate"
    STRICT = "strict"


# Refund rules: list of (days_before_checkin, refund_percentage)
# Evaluated in order - first match wins
POLICY_RULES: dict[CancellationPolicy, list[tuple[int, Decimal]]] = {
    CancellationPolicy.FLEXIBLE: [
        (1, Decimal("100")),   # 24h+ before: 100% refund
        (0, Decimal("50")),    # <24h: 50% refund
    ],
    CancellationPolicy.MODERATE: [
        (5, Decimal("100")),   # 5+ days before: 100% refund
        (1, Decimal("50")),    # 1-5 days before: 50% refund
        (0, Decimal("0")),     # <24h: no refund
    ],
    CancellationPolicy.STRICT: [
        (7, Decimal("50")),    # 7+ days before: 50% refund
        (0, Decimal("0")),     # <7 days: no refund
    ],
}


def calculate_refund_percentage(
    policy: str | CancellationPolicy,
    check_in_date: date,
    cancellation_date: date,
) -> Decimal:
    """Calculate refund percentage based on policy and timing.

    Args:
        policy: The cancellation policy type
        check_in_date: Booking check-in date
        cancellation_date: Date of cancellation

    Returns:
        Decimal: Refund percentage (0-100)
    """
    if isinstance(policy, str):
        try:
            policy = CancellationPolicy(policy)
        except ValueError:
            # Default to moderate for unknown policies
            policy = CancellationPolicy.MODERATE

    days_before = (check_in_date - cancellation_date).days

    rules = POLICY_RULES.get(policy, POLICY_RULES[CancellationPolicy.MODERATE])

    for min_days, refund_pct in rules:
        if days_before >= min_days:
            return refund_pct

    return Decimal("0")


def calculate_refund_amount(
    policy: str | CancellationPolicy,
    check_in_date: date,
    cancellation_date: date,
    total_price: int,
) -> int:
    """Calculate refund amount in smallest currency unit.

    Args:
        policy: The cancellation policy type
        check_in_date: Booking check-in date
        cancellation_date: Date of cancellation
        total_price: Total booking price in paisa

    Returns:
        int: Refund amount in paisa
    """
    refund_pct = calculate_refund_percentage(policy, check_in_date, cancellation_date)
    refund_amount = (Decimal(total_price) * refund_pct / Decimal("100")).quantize(Decimal("1"))
    return int(refund_amount)


def get_policy_description(policy: str | CancellationPolicy) -> str:
    """Get human-readable policy description."""
    descriptions = {
        CancellationPolicy.FLEXIBLE: (
            "Full refund up to 24 hours before check-in. "
            "50% refund if cancelled less than 24 hours before."
        ),
        CancellationPolicy.MODERATE: (
            "Full refund up to 5 days before check-in. "
            "50% refund if cancelled 1-5 days before. "
            "No refund if cancelled less than 24 hours before."
        ),
        CancellationPolicy.STRICT: (
            "50% refund up to 7 days before check-in. "
            "No refund if cancelled less than 7 days before."
        ),
    }

    if isinstance(policy, str):
        try:
            policy = CancellationPolicy(policy)
        except ValueError:
            return "Unknown cancellation policy"

    return descriptions.get(policy, "Unknown cancellation policy")
