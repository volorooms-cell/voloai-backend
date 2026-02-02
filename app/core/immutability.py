"""Immutability enforcement for financial records using SQLAlchemy events."""

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session, UOWTransaction

from app.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


class ImmutabilityViolationError(ValidationError):
    """Raised when attempting to modify immutable financial records."""

    def __init__(self, model_name: str, operation: str, record_id: str):
        self.model_name = model_name
        self.operation = operation
        self.record_id = record_id
        super().__init__(
            f"Immutability violation: Cannot {operation} {model_name} record {record_id}. "
            "Financial records are immutable after creation."
        )


def _log_immutability_violation(model_name: str, operation: str, record_id: str) -> None:
    """Log immutability violation for audit purposes."""
    logger.error(
        f"IMMUTABILITY_VIOLATION: Attempted to {operation} {model_name} "
        f"record_id={record_id} at {datetime.now(UTC).isoformat()}"
    )


def register_immutability_enforcement():
    """Register SQLAlchemy event listeners for immutability enforcement.

    Must be called after models are imported but before session use.
    """
    from app.models.financial import BookingFinancialSnapshot, SettlementLedgerEntry
    from app.models.admin import AuditLog

    # ============ BookingFinancialSnapshot: No UPDATE, No DELETE ============

    @event.listens_for(BookingFinancialSnapshot, "before_update")
    def prevent_snapshot_update(mapper, connection, target):
        """Prevent updates to BookingFinancialSnapshot."""
        _log_immutability_violation(
            "BookingFinancialSnapshot", "UPDATE", str(target.id)
        )
        raise ImmutabilityViolationError(
            "BookingFinancialSnapshot", "UPDATE", str(target.id)
        )

    @event.listens_for(BookingFinancialSnapshot, "before_delete")
    def prevent_snapshot_delete(mapper, connection, target):
        """Prevent deletion of BookingFinancialSnapshot."""
        _log_immutability_violation(
            "BookingFinancialSnapshot", "DELETE", str(target.id)
        )
        raise ImmutabilityViolationError(
            "BookingFinancialSnapshot", "DELETE", str(target.id)
        )

    # ============ SettlementLedgerEntry: Append-Only ============

    @event.listens_for(SettlementLedgerEntry, "before_update")
    def prevent_ledger_update(mapper, connection, target):
        """Prevent updates to SettlementLedgerEntry (append-only)."""
        _log_immutability_violation(
            "SettlementLedgerEntry", "UPDATE", str(target.id)
        )
        raise ImmutabilityViolationError(
            "SettlementLedgerEntry", "UPDATE", str(target.id)
        )

    @event.listens_for(SettlementLedgerEntry, "before_delete")
    def prevent_ledger_delete(mapper, connection, target):
        """Prevent deletion of SettlementLedgerEntry (append-only)."""
        _log_immutability_violation(
            "SettlementLedgerEntry", "DELETE", str(target.id)
        )
        raise ImmutabilityViolationError(
            "SettlementLedgerEntry", "DELETE", str(target.id)
        )

    # ============ AuditLog: Append-Only ============

    @event.listens_for(AuditLog, "before_update")
    def prevent_audit_update(mapper, connection, target):
        """Prevent updates to AuditLog (append-only)."""
        _log_immutability_violation(
            "AuditLog", "UPDATE", str(target.id)
        )
        raise ImmutabilityViolationError(
            "AuditLog", "UPDATE", str(target.id)
        )

    @event.listens_for(AuditLog, "before_delete")
    def prevent_audit_delete(mapper, connection, target):
        """Prevent deletion of AuditLog (append-only)."""
        _log_immutability_violation(
            "AuditLog", "DELETE", str(target.id)
        )
        raise ImmutabilityViolationError(
            "AuditLog", "DELETE", str(target.id)
        )

    logger.info("Immutability enforcement registered for financial records")
