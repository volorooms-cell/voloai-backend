"""Financial audit trail service."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import AuditLog


class AuditService:
    """Service for immutable financial audit logging."""

    # Financial actions that require audit logging
    FINANCIAL_ACTIONS = {
        "payment_mark_paid",
        "payment_mark_failed",
        "refund_create",
        "refund_approve",
        "payout_mark_eligible",
        "payout_release",
        "payout_reverse",
        "dispute_open",
        "dispute_resolve",
        "dispute_reverse",
        "snapshot_create",
    }

    async def log_financial_action(
        self,
        db: AsyncSession,
        user_id: UUID,
        action: str,
        resource_type: str,
        resource_id: UUID,
        old_values: dict[str, Any] | None = None,
        new_values: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuditLog:
        """Log a financial action (immutable).

        Args:
            db: Database session
            user_id: User performing the action
            action: Action name (e.g., "payment_mark_paid")
            resource_type: Resource type (e.g., "payment", "payout")
            resource_id: Resource ID
            old_values: Previous state
            new_values: New state
            ip_address: Client IP
            user_agent: Client user agent

        Returns:
            Created audit log entry
        """
        audit = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            old_values=old_values,
            new_values=new_values,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.add(audit)
        return audit

    async def log_payment_action(
        self,
        db: AsyncSession,
        user_id: UUID,
        action: str,
        payment_id: UUID,
        old_status: str,
        new_status: str,
        amount: int | None = None,
        ip_address: str | None = None,
    ) -> AuditLog:
        """Log payment status change."""
        return await self.log_financial_action(
            db=db,
            user_id=user_id,
            action=action,
            resource_type="payment",
            resource_id=payment_id,
            old_values={"status": old_status},
            new_values={"status": new_status, "amount": amount} if amount else {"status": new_status},
            ip_address=ip_address,
        )

    async def log_refund_action(
        self,
        db: AsyncSession,
        user_id: UUID,
        action: str,
        refund_id: UUID,
        payment_id: UUID,
        amount: int,
        reason: str,
        ip_address: str | None = None,
    ) -> AuditLog:
        """Log refund creation/approval."""
        return await self.log_financial_action(
            db=db,
            user_id=user_id,
            action=action,
            resource_type="refund",
            resource_id=refund_id,
            new_values={
                "payment_id": str(payment_id),
                "amount": amount,
                "reason": reason,
            },
            ip_address=ip_address,
        )

    async def log_payout_action(
        self,
        db: AsyncSession,
        user_id: UUID,
        action: str,
        payout_id: UUID,
        old_status: str,
        new_status: str,
        amount: int,
        host_id: UUID,
        ip_address: str | None = None,
    ) -> AuditLog:
        """Log payout status change."""
        return await self.log_financial_action(
            db=db,
            user_id=user_id,
            action=action,
            resource_type="payout",
            resource_id=payout_id,
            old_values={"status": old_status},
            new_values={
                "status": new_status,
                "amount": amount,
                "host_id": str(host_id),
            },
            ip_address=ip_address,
        )

    async def log_dispute_action(
        self,
        db: AsyncSession,
        user_id: UUID,
        action: str,
        dispute_id: UUID,
        old_status: str | None,
        new_status: str,
        resolution_type: str | None = None,
        amount: int = 0,
        ip_address: str | None = None,
    ) -> AuditLog:
        """Log dispute action."""
        new_values: dict[str, Any] = {"status": new_status}
        if resolution_type:
            new_values["resolution_type"] = resolution_type
        if amount:
            new_values["amount"] = amount

        return await self.log_financial_action(
            db=db,
            user_id=user_id,
            action=action,
            resource_type="dispute",
            resource_id=dispute_id,
            old_values={"status": old_status} if old_status else None,
            new_values=new_values,
            ip_address=ip_address,
        )


audit_service = AuditService()
