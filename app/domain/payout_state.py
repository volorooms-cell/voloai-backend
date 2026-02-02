"""Host payout state machine.

States:
- pending: Booking completed, payout not yet eligible
- eligible: Payout ready to be released (hold period passed)
- released: Payout sent to host
- reversed: Payout reversed due to refund/dispute
"""

from app.core.exceptions import ValidationError

PAYOUT_TRANSITIONS = {
    "pending": {"eligible", "reversed"},
    "eligible": {"released", "reversed"},
    "released": {"reversed"},
    "reversed": set(),
}


def assert_payout_transition(current: str, target: str) -> None:
    """Validate payout state transition.

    Args:
        current: Current payout status
        target: Target payout status

    Raises:
        ValidationError: If transition is not allowed
    """
    allowed = PAYOUT_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise ValidationError(
            f"Invalid payout transition: {current} → {target}"
        )


def can_release_payout(booking_status: str, payment_status: str) -> tuple[bool, str | None]:
    """Check if payout can be released based on booking/payment state.

    Args:
        booking_status: Current booking status
        payment_status: Current payment status

    Returns:
        Tuple of (can_release, error_message)
    """
    if booking_status == "cancelled":
        return False, "Cannot release payout for cancelled booking"

    if payment_status in ("refunded", "partially_refunded"):
        return False, "Cannot release payout for refunded booking"

    if payment_status != "paid":
        return False, "Cannot release payout - payment not completed"

    if booking_status not in ("completed", "checked_in"):
        return False, f"Cannot release payout - booking status is {booking_status}"

    return True, None
