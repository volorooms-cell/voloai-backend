"""Settlement and reconciliation service.

Handles financial snapshots, ledger entries, and reconciliation.
"""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.models.booking import Booking
from app.models.financial import (
    BookingFinancialSnapshot,
    ReconciliationPeriod,
    SettlementLedgerEntry,
)
from app.models.payment import HostPayout, Payment, Refund


def assert_positive_amount(amount: int, context: str) -> None:
    """Guard: Prevent negative or zero amounts."""
    if amount <= 0:
        raise ValidationError(f"{context}: amount must be positive, got {amount}")


def assert_no_duplicate_ledger_entry(
    existing_entry: SettlementLedgerEntry | None, entry_type: str, reference_id: UUID
) -> None:
    """Guard: Prevent duplicate ledger entries for the same operation."""
    if existing_entry is not None:
        raise ValidationError(
            f"Duplicate {entry_type} ledger entry for reference {reference_id}"
        )


class SettlementService:
    """Service for settlement and reconciliation operations."""

    async def create_booking_snapshot(
        self,
        db: AsyncSession,
        booking: Booking,
    ) -> BookingFinancialSnapshot:
        """Create immutable financial snapshot for a completed booking.

        Args:
            db: Database session
            booking: Completed booking

        Returns:
            BookingFinancialSnapshot: Immutable snapshot record
        """
        # Check if snapshot already exists
        existing = await db.execute(
            select(BookingFinancialSnapshot).where(
                BookingFinancialSnapshot.booking_id == booking.id
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Snapshot already exists for booking {booking.id}")

        snapshot = BookingFinancialSnapshot(
            booking_id=booking.id,
            booking_number=booking.booking_number,
            guest_total=booking.total_price,
            guest_subtotal=booking.subtotal,
            guest_cleaning_fee=booking.cleaning_fee,
            guest_service_fee=booking.service_fee,
            guest_taxes=booking.taxes,
            commission_rate=booking.commission_rate,
            commission_amount=booking.commission_amount,
            host_payout_amount=booking.host_payout_amount,
            currency=booking.currency,
            check_in=booking.check_in,
            check_out=booking.check_out,
            nights=booking.nights,
            nightly_rate=booking.nightly_rate,
            guest_id=booking.guest_id,
            host_id=booking.host_id,
            listing_id=booking.listing_id,
            source=booking.source,
        )
        db.add(snapshot)
        return snapshot

    async def record_payment_received(
        self,
        db: AsyncSession,
        payment: Payment,
        booking: Booking,
    ) -> SettlementLedgerEntry:
        """Record a payment received in the ledger.

        Args:
            db: Database session
            payment: Completed payment
            booking: Associated booking

        Returns:
            SettlementLedgerEntry: Ledger entry
        """
        # Guard: positive amount
        assert_positive_amount(payment.amount, "Payment")

        # Guard: no duplicate entry
        existing = await db.execute(
            select(SettlementLedgerEntry).where(
                SettlementLedgerEntry.payment_id == payment.id,
                SettlementLedgerEntry.entry_type == "payment_received",
            )
        )
        assert_no_duplicate_ledger_entry(
            existing.scalar_one_or_none(), "payment_received", payment.id
        )

        entry = SettlementLedgerEntry(
            entry_type="payment_received",
            direction="credit",
            amount=payment.amount,
            currency=payment.currency,
            booking_id=booking.id,
            payment_id=payment.id,
            counterparty_type="guest",
            counterparty_id=payment.user_id,
            gateway=payment.gateway,
            gateway_transaction_id=payment.gateway_transaction_id,
            description=f"Payment for booking {booking.booking_number}",
            effective_date=datetime.now(UTC).date(),
        )
        db.add(entry)
        return entry

    async def record_refund_issued(
        self,
        db: AsyncSession,
        refund: Refund,
        booking: Booking,
        payment: Payment,
    ) -> SettlementLedgerEntry:
        """Record a refund issued in the ledger.

        Args:
            db: Database session
            refund: Issued refund
            booking: Associated booking
            payment: Original payment

        Returns:
            SettlementLedgerEntry: Ledger entry
        """
        # Guard: positive amount
        assert_positive_amount(refund.amount, "Refund")

        # Guard: no duplicate entry
        existing = await db.execute(
            select(SettlementLedgerEntry).where(
                SettlementLedgerEntry.refund_id == refund.id,
                SettlementLedgerEntry.entry_type == "refund_issued",
            )
        )
        assert_no_duplicate_ledger_entry(
            existing.scalar_one_or_none(), "refund_issued", refund.id
        )

        entry = SettlementLedgerEntry(
            entry_type="refund_issued",
            direction="debit",
            amount=refund.amount,
            currency=payment.currency,
            booking_id=booking.id,
            payment_id=payment.id,
            refund_id=refund.id,
            counterparty_type="guest",
            counterparty_id=payment.user_id,
            gateway=payment.gateway,
            gateway_transaction_id=refund.gateway_refund_id,
            description=f"Refund for booking {booking.booking_number}: {refund.reason}",
            effective_date=datetime.now(UTC).date(),
        )
        db.add(entry)
        return entry

    async def record_payout_released(
        self,
        db: AsyncSession,
        payout: HostPayout,
        booking: Booking | None = None,
    ) -> SettlementLedgerEntry:
        """Record a payout released in the ledger.

        Args:
            db: Database session
            payout: Released payout
            booking: Associated booking (if any)

        Returns:
            SettlementLedgerEntry: Ledger entry
        """
        # Guard: positive amount (prevent negative payouts)
        assert_positive_amount(payout.amount, "Payout")

        # Guard: no duplicate entry (prevent double settlement)
        existing = await db.execute(
            select(SettlementLedgerEntry).where(
                SettlementLedgerEntry.payout_id == payout.id,
                SettlementLedgerEntry.entry_type == "payout_released",
            )
        )
        assert_no_duplicate_ledger_entry(
            existing.scalar_one_or_none(), "payout_released", payout.id
        )

        description = f"Payout to host"
        if booking:
            description = f"Payout for booking {booking.booking_number}"

        entry = SettlementLedgerEntry(
            entry_type="payout_released",
            direction="debit",
            amount=payout.amount,
            currency=payout.currency,
            booking_id=payout.booking_id,
            payout_id=payout.id,
            counterparty_type="host",
            counterparty_id=payout.host_id,
            gateway=payout.payout_method,
            gateway_transaction_id=payout.gateway_transaction_id,
            description=description,
            effective_date=payout.payout_date,
        )
        db.add(entry)
        return entry

    async def record_payout_reversed(
        self,
        db: AsyncSession,
        payout: HostPayout,
        booking: Booking | None = None,
    ) -> SettlementLedgerEntry:
        """Record a payout reversal in the ledger.

        Args:
            db: Database session
            payout: Reversed payout
            booking: Associated booking (if any)

        Returns:
            SettlementLedgerEntry: Ledger entry
        """
        # Guard: positive amount
        assert_positive_amount(payout.amount, "Payout reversal")

        # Guard: no duplicate reversal entry
        existing = await db.execute(
            select(SettlementLedgerEntry).where(
                SettlementLedgerEntry.payout_id == payout.id,
                SettlementLedgerEntry.entry_type == "payout_reversed",
            )
        )
        assert_no_duplicate_ledger_entry(
            existing.scalar_one_or_none(), "payout_reversed", payout.id
        )

        description = f"Payout reversal"
        if booking:
            description = f"Payout reversal for booking {booking.booking_number}"

        entry = SettlementLedgerEntry(
            entry_type="payout_reversed",
            direction="credit",  # Money comes back to VOLO
            amount=payout.amount,
            currency=payout.currency,
            booking_id=payout.booking_id,
            payout_id=payout.id,
            counterparty_type="host",
            counterparty_id=payout.host_id,
            description=description,
            effective_date=datetime.now(UTC).date(),
        )
        db.add(entry)
        return entry

    async def get_or_create_reconciliation_period(
        self,
        db: AsyncSession,
        target_date: date,
        period_type: str = "daily",
    ) -> ReconciliationPeriod:
        """Get or create a reconciliation period for a date.

        Args:
            db: Database session
            target_date: Date to find/create period for
            period_type: Period type (daily, weekly, monthly)

        Returns:
            ReconciliationPeriod: The period record
        """
        if period_type == "daily":
            period_start = target_date
            period_end = target_date
        elif period_type == "weekly":
            # Week starts on Monday
            period_start = target_date - timedelta(days=target_date.weekday())
            period_end = period_start + timedelta(days=6)
        elif period_type == "monthly":
            period_start = target_date.replace(day=1)
            next_month = period_start.replace(day=28) + timedelta(days=4)
            period_end = next_month - timedelta(days=next_month.day)
        else:
            period_start = target_date
            period_end = target_date

        # Check if period exists
        existing = await db.execute(
            select(ReconciliationPeriod).where(
                ReconciliationPeriod.period_start == period_start,
                ReconciliationPeriod.period_end == period_end,
                ReconciliationPeriod.period_type == period_type,
            )
        )
        period = existing.scalar_one_or_none()

        if not period:
            period = ReconciliationPeriod(
                period_start=period_start,
                period_end=period_end,
                period_type=period_type,
                status="open",
            )
            db.add(period)

        return period

    async def update_period_totals(
        self,
        db: AsyncSession,
        period: ReconciliationPeriod,
    ) -> ReconciliationPeriod:
        """Recalculate totals for a reconciliation period.

        Args:
            db: Database session
            period: Period to update

        Returns:
            ReconciliationPeriod: Updated period
        """
        from sqlalchemy import func

        # Sum payments
        payments_result = await db.execute(
            select(func.sum(SettlementLedgerEntry.amount), func.count())
            .where(
                SettlementLedgerEntry.entry_type == "payment_received",
                SettlementLedgerEntry.effective_date >= period.period_start,
                SettlementLedgerEntry.effective_date <= period.period_end,
            )
        )
        payments_sum, payments_count = payments_result.one()
        period.total_payments_received = payments_sum or 0
        period.payment_count = payments_count or 0

        # Sum refunds
        refunds_result = await db.execute(
            select(func.sum(SettlementLedgerEntry.amount), func.count())
            .where(
                SettlementLedgerEntry.entry_type == "refund_issued",
                SettlementLedgerEntry.effective_date >= period.period_start,
                SettlementLedgerEntry.effective_date <= period.period_end,
            )
        )
        refunds_sum, refunds_count = refunds_result.one()
        period.total_refunds_issued = refunds_sum or 0
        period.refund_count = refunds_count or 0

        # Sum payouts
        payouts_result = await db.execute(
            select(func.sum(SettlementLedgerEntry.amount), func.count())
            .where(
                SettlementLedgerEntry.entry_type == "payout_released",
                SettlementLedgerEntry.effective_date >= period.period_start,
                SettlementLedgerEntry.effective_date <= period.period_end,
            )
        )
        payouts_sum, payouts_count = payouts_result.one()
        period.total_payouts_released = payouts_sum or 0
        period.payout_count = payouts_count or 0

        # Calculate net position
        period.net_position = (
            period.total_payments_received
            - period.total_refunds_issued
            - period.total_payouts_released
        )

        return period


    async def check_ledger_balance(
        self,
        db: AsyncSession,
    ) -> tuple[bool, int]:
        """Check if ledger is balanced (credits == debits for closed periods).

        Returns:
            Tuple of (is_balanced, imbalance_amount)
        """
        # Sum all credits
        credits_result = await db.execute(
            select(func.coalesce(func.sum(SettlementLedgerEntry.amount), 0)).where(
                SettlementLedgerEntry.direction == "credit"
            )
        )
        total_credits = credits_result.scalar() or 0

        # Sum all debits
        debits_result = await db.execute(
            select(func.coalesce(func.sum(SettlementLedgerEntry.amount), 0)).where(
                SettlementLedgerEntry.direction == "debit"
            )
        )
        total_debits = debits_result.scalar() or 0

        # Net position should be >= 0 (more credits than debits = money held)
        imbalance = total_credits - total_debits
        # Negative imbalance means we paid out more than received - critical error
        is_balanced = imbalance >= 0

        return is_balanced, imbalance


# Singleton instance
settlement_service = SettlementService()
