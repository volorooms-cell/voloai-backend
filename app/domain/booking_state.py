"""Booking state machine."""

from app.core.exceptions import ValidationError

BOOKING_TRANSITIONS = {
    "pending": {"confirmed", "cancelled"},
    "confirmed": {"checked_in", "cancelled"},
    "checked_in": {"completed"},
    "completed": set(),
    "cancelled": set(),
}


def assert_booking_transition(current: str, target: str) -> None:
    allowed = BOOKING_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise ValidationError(
            f"Invalid booking transition: {current} → {target}"
        )
