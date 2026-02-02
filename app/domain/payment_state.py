"""Payment state machine."""

from app.core.exceptions import ValidationError

PAYMENT_TRANSITIONS = {
    "pending": {"processing", "completed", "failed"},
    "processing": {"completed", "failed"},
    "completed": {"refunded"},
    "failed": set(),
    "refunded": set(),
}


def assert_payment_transition(current: str, target: str) -> None:
    allowed = PAYMENT_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise ValidationError(
            f"Invalid payment transition: {current} → {target}"
        )
