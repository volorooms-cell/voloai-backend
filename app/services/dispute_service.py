"""Dispute and chargeback service."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.dispute_state import (
    VALID_RESOLUTION_TYPES,
    assert_dispute_transition,
    can_resolve_dispute,
    can_reverse_dispute,
)
from app.models.admin import Dispute
from app.models.booking import Booking
from app.models.financial import SettlementLedgerEntry
from app.models.payment import HostPayout


class DisputeService:
    """Service for dispute and chargeback lifecycle."""

    async def open_dispute(
        self,
        db: AsyncSession,
        booking_id: UUID,
        raised_by: UUID,
        against_id: UUID,
        category: str,
        description: str,
        evidence_urls: list[str] | None = None,
    ) -> Dispute:
        """Open a new dispute."""
        dispute = Dispute(
            booking_id=booking_id,
            raised_by=raised_by,
            against_id=against_id,
            category=category,
            description=description,
            evidence_urls=evidence_urls,
            status="opened",
        )
        db.add(dispute)
        await db.flush()

        # Create ledger entry for dispute opened
        await self._create_dispute_ledger_entry(
            db,
            dispute,
            entry_type="dispute_opened",
            description=f"Dispute opened: {category}",
        )

        return dispute

    async def start_review(
        self,
        db: AsyncSession,
        dispute_id: UUID,
        assigned_to: UUID,
    ) -> Dispute:
        """Move dispute to under_review status."""
        dispute = await self._get_dispute(db, dispute_id)
        assert_dispute_transition(dispute.status, "under_review")

        dispute.status = "under_review"
        dispute.assigned_to = assigned_to

        return dispute

    async def resolve_dispute(
        self,
        db: AsyncSession,
        dispute_id: UUID,
        resolved_by: UUID,
        resolution: str,
        resolution_type: str,
        refund_amount: int = 0,
        payout_adjustment: int = 0,
    ) -> Dispute:
        """Resolve a dispute with optional financial adjustments."""
        if resolution_type not in VALID_RESOLUTION_TYPES:
            from app.core.exceptions import ValidationError
            raise ValidationError(f"Invalid resolution type: {resolution_type}")

        dispute = await self._get_dispute(db, dispute_id)
        can_resolve, error = can_resolve_dispute(dispute.status)
        if not can_resolve:
            from app.core.exceptions import ValidationError
            raise ValidationError(error)

        assert_dispute_transition(dispute.status, "resolved")

        dispute.status = "resolved"
        dispute.resolution = resolution
        dispute.resolution_type = resolution_type
        dispute.refund_granted = refund_amount
        dispute.payout_adjusted = payout_adjustment
        dispute.resolved_by = resolved_by
        dispute.resolved_at = datetime.now(UTC)

        # Handle financial adjustments based on resolution type
        if resolution_type == "payout_reversal" and payout_adjustment > 0:
            await self._adjust_payout_for_dispute(db, dispute, payout_adjustment)

        # Create ledger entry for resolution
        await self._create_dispute_ledger_entry(
            db,
            dispute,
            entry_type="dispute_resolved",
            description=f"Dispute resolved: {resolution_type}",
            amount=refund_amount or payout_adjustment,
        )

        return dispute

    async def reverse_resolution(
        self,
        db: AsyncSession,
        dispute_id: UUID,
        reversed_by: UUID,
        reason: str,
    ) -> Dispute:
        """Reverse a dispute resolution (e.g., chargeback won after initial loss)."""
        dispute = await self._get_dispute(db, dispute_id)
        can_reverse, error = can_reverse_dispute(dispute.status)
        if not can_reverse:
            from app.core.exceptions import ValidationError
            raise ValidationError(error)

        assert_dispute_transition(dispute.status, "reversed")

        old_resolution_type = dispute.resolution_type
        dispute.status = "reversed"
        dispute.resolution = f"{dispute.resolution}\n\nREVERSED: {reason}"

        # Create ledger entry for reversal
        await self._create_dispute_ledger_entry(
            db,
            dispute,
            entry_type="dispute_reversed",
            description=f"Dispute resolution reversed: {reason}",
            amount=dispute.refund_granted or dispute.payout_adjusted,
        )

        return dispute

    async def _get_dispute(self, db: AsyncSession, dispute_id: UUID) -> Dispute:
        """Get dispute by ID or raise NotFoundError."""
        result = await db.execute(select(Dispute).where(Dispute.id == dispute_id))
        dispute = result.scalar_one_or_none()
        if not dispute:
            from app.core.exceptions import NotFoundError
            raise NotFoundError("Dispute", str(dispute_id))
        return dispute

    async def _adjust_payout_for_dispute(
        self,
        db: AsyncSession,
        dispute: Dispute,
        adjustment_amount: int,
    ) -> None:
        """Adjust host payout based on dispute resolution."""
        # Find the payout for this booking
        payout_result = await db.execute(
            select(HostPayout).where(HostPayout.booking_id == dispute.booking_id)
        )
        payout = payout_result.scalar_one_or_none()

        if payout and payout.status in ("pending", "eligible"):
            # Reduce or reverse the payout
            if adjustment_amount >= payout.amount:
                payout.status = "reversed"
            else:
                payout.amount = payout.amount - adjustment_amount

    async def _create_dispute_ledger_entry(
        self,
        db: AsyncSession,
        dispute: Dispute,
        entry_type: str,
        description: str,
        amount: int = 0,
    ) -> SettlementLedgerEntry:
        """Create a ledger entry for dispute activity."""
        # Determine direction based on entry type
        direction = "debit" if entry_type == "dispute_resolved" else "credit"
        if entry_type == "dispute_reversed":
            direction = "credit"  # Reversal brings money back
        if entry_type == "dispute_opened":
            direction = "debit"  # Potential liability
            amount = 0  # No amount until resolved

        entry = SettlementLedgerEntry(
            entry_type=entry_type,
            direction=direction,
            amount=amount,
            currency="PKR",
            booking_id=dispute.booking_id,
            counterparty_type="dispute",
            counterparty_id=dispute.id,
            description=description,
            effective_date=datetime.now(UTC).date(),
        )
        db.add(entry)
        return entry


dispute_service = DisputeService()
