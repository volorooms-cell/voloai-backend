"""Idempotency protection for financial operations."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError


class IdempotencyStore:
    """In-memory idempotency key store.

    In production, use Redis or database for persistence across restarts.
    """

    def __init__(self):
        self._keys: dict[str, dict] = {}
        self._ttl = timedelta(hours=24)

    def _cleanup_expired(self) -> None:
        """Remove expired keys."""
        now = datetime.now(UTC)
        expired = [k for k, v in self._keys.items() if v["expires_at"] < now]
        for k in expired:
            del self._keys[k]

    def get(self, key: str) -> dict | None:
        """Get stored result for idempotency key."""
        self._cleanup_expired()
        entry = self._keys.get(key)
        if entry and entry["expires_at"] > datetime.now(UTC):
            return entry["result"]
        return None

    def set(self, key: str, result: dict) -> None:
        """Store result for idempotency key."""
        self._keys[key] = {
            "result": result,
            "expires_at": datetime.now(UTC) + self._ttl,
        }

    def exists(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        return self.get(key) is not None


# Global store instance
_idempotency_store = IdempotencyStore()


def generate_idempotency_key(
    operation: str,
    entity_id: UUID | str,
    params: dict[str, Any] | None = None,
) -> str:
    """Generate a deterministic idempotency key.

    Args:
        operation: Operation name (e.g., "payment_mark_paid", "refund_create")
        entity_id: Primary entity ID
        params: Additional parameters to include in key

    Returns:
        SHA256 hash of operation + entity + params
    """
    key_data = {
        "operation": operation,
        "entity_id": str(entity_id),
        "params": params or {},
    }
    key_str = json.dumps(key_data, sort_keys=True)
    return hashlib.sha256(key_str.encode()).hexdigest()


def check_idempotency(key: str) -> dict | None:
    """Check if operation was already performed.

    Returns:
        Previous result if found, None otherwise
    """
    return _idempotency_store.get(key)


def store_idempotency_result(key: str, result: dict) -> None:
    """Store operation result for idempotency."""
    _idempotency_store.set(key, result)


class IdempotencyError(ValidationError):
    """Raised when duplicate operation is detected."""

    def __init__(self, operation: str, entity_id: str):
        super().__init__(
            f"Duplicate {operation} operation for entity {entity_id}. "
            "This operation was already processed."
        )


def require_idempotency(operation: str):
    """Decorator for idempotent financial operations.

    The decorated function must have entity_id as first positional arg
    after self/db parameters.
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Extract entity_id from args or kwargs
            entity_id = kwargs.get("entity_id") or kwargs.get("payment_id") or kwargs.get("payout_id")
            if not entity_id and len(args) > 2:
                entity_id = args[2]  # Assuming (self, db, entity_id, ...)

            if not entity_id:
                return await func(*args, **kwargs)

            # Generate key
            key = generate_idempotency_key(operation, entity_id)

            # Check for existing result
            existing = check_idempotency(key)
            if existing:
                raise IdempotencyError(operation, str(entity_id))

            # Execute operation
            result = await func(*args, **kwargs)

            # Store result (just mark as completed)
            store_idempotency_result(key, {"completed": True, "at": datetime.now(UTC).isoformat()})

            return result
        return wrapper
    return decorator
