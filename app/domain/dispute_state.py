"""Dispute state machine.

States: opened → under_review → resolved → reversed
"""

from app.core.exceptions import ValidationError

DISPUTE_TRANSITIONS: dict[str, set[str]] = {
    "opened": {"under_review", "resolved"},
    "under_review": {"resolved", "opened"},  # Can reopen if more info needed
    "resolved": {"reversed"},
    "reversed": set(),  # Terminal state
}

VALID_RESOLUTION_TYPES = {
    "refund",
    "payout_reversal",
    "no_action",
    "chargeback_won",
    "chargeback_lost",
}


def assert_dispute_transition(current_status: str, new_status: str) -> None:
    """Validate dispute state transition."""
    allowed = DISPUTE_TRANSITIONS.get(current_status, set())
    if new_status not in allowed:
        raise ValidationError(f"Invalid dispute transition: {current_status} → {new_status}")


def can_resolve_dispute(status: str) -> tuple[bool, str | None]:
    """Check if dispute can be resolved."""
    if status == "reversed":
        return False, "Dispute has already been reversed"
    if status == "resolved":
        return False, "Dispute is already resolved"
    return True, None


def can_reverse_dispute(status: str) -> tuple[bool, str | None]:
    """Check if dispute can be reversed."""
    if status != "resolved":
        return False, "Only resolved disputes can be reversed"
    return True, None
