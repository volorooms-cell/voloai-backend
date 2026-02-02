"""Financial health check service (read-only validation)."""

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, and_, exists
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.financial import BookingFinancialSnapshot, SettlementLedgerEntry
from app.models.payment import HostPayout, Payment, Refund


class HealthStatus(str, Enum):
    OK = "OK"
    WARNING = "WARNING"
    ERROR = "ERROR"


class FinanceHealthService:
    """Read-only financial integrity validator."""

    async def run_all_checks(self, db: AsyncSession) -> dict[str, Any]:
        """Run all financial health checks."""
        checks = []
        overall_status = HealthStatus.OK

        # Run each check
        check_methods = [
            self._check_booking_snapshot_coverage,
            self._check_ledger_references,
            self._check_ledger_math_consistency,
            self._check_payout_booking_state,
            self._check_refund_payment_state,
            self._check_ledger_snapshot_requirement,
            self._check_duplicate_snapshots,
            self._check_orphan_payouts,
        ]

        for check_method in check_methods:
            result = await check_method(db)
            checks.append(result)

            # Update overall status
            if result["status"] == HealthStatus.ERROR:
                overall_status = HealthStatus.ERROR
            elif result["status"] == HealthStatus.WARNING and overall_status != HealthStatus.ERROR:
                overall_status = HealthStatus.WARNING

        # Get counts
        counts = await self._get_counts(db)

        return {
            "status": overall_status,
            "checks": checks,
            "counts": counts,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def _check_booking_snapshot_coverage(self, db: AsyncSession) -> dict:
        """Every completed booking must have exactly ONE snapshot."""
        # Completed bookings without snapshots
        missing_result = await db.execute(
            select(func.count()).select_from(Booking).where(
                Booking.status == "completed",
                ~exists(
                    select(BookingFinancialSnapshot.id).where(
                        BookingFinancialSnapshot.booking_id == Booking.id
                    )
                )
            )
        )
        missing_count = missing_result.scalar() or 0

        if missing_count > 0:
            return {
                "name": "booking_snapshot_coverage",
                "status": HealthStatus.ERROR,
                "message": f"{missing_count} completed booking(s) missing financial snapshot",
                "details": {"missing_count": missing_count},
            }

        return {
            "name": "booking_snapshot_coverage",
            "status": HealthStatus.OK,
            "message": "All completed bookings have snapshots",
            "details": {},
        }

    async def _check_duplicate_snapshots(self, db: AsyncSession) -> dict:
        """No booking should have more than one snapshot."""
        duplicate_result = await db.execute(
            select(
                BookingFinancialSnapshot.booking_id,
                func.count().label("cnt")
            )
            .group_by(BookingFinancialSnapshot.booking_id)
            .having(func.count() > 1)
        )
        duplicates = duplicate_result.all()

        if duplicates:
            return {
                "name": "duplicate_snapshots",
                "status": HealthStatus.ERROR,
                "message": f"{len(duplicates)} booking(s) have duplicate snapshots",
                "details": {"booking_ids": [str(d[0]) for d in duplicates]},
            }

        return {
            "name": "duplicate_snapshots",
            "status": HealthStatus.OK,
            "message": "No duplicate snapshots found",
            "details": {},
        }

    async def _check_ledger_references(self, db: AsyncSession) -> dict:
        """Every ledger entry must reference valid entities."""
        issues = []

        # Check booking references
        invalid_booking_result = await db.execute(
            select(func.count()).select_from(SettlementLedgerEntry).where(
                SettlementLedgerEntry.booking_id.isnot(None),
                ~exists(
                    select(Booking.id).where(
                        Booking.id == SettlementLedgerEntry.booking_id
                    )
                )
            )
        )
        invalid_bookings = invalid_booking_result.scalar() or 0
        if invalid_bookings > 0:
            issues.append(f"{invalid_bookings} entries with invalid booking_id")

        # Check payment references
        invalid_payment_result = await db.execute(
            select(func.count()).select_from(SettlementLedgerEntry).where(
                SettlementLedgerEntry.payment_id.isnot(None),
                ~exists(
                    select(Payment.id).where(
                        Payment.id == SettlementLedgerEntry.payment_id
                    )
                )
            )
        )
        invalid_payments = invalid_payment_result.scalar() or 0
        if invalid_payments > 0:
            issues.append(f"{invalid_payments} entries with invalid payment_id")

        # Check payout references
        invalid_payout_result = await db.execute(
            select(func.count()).select_from(SettlementLedgerEntry).where(
                SettlementLedgerEntry.payout_id.isnot(None),
                ~exists(
                    select(HostPayout.id).where(
                        HostPayout.id == SettlementLedgerEntry.payout_id
                    )
                )
            )
        )
        invalid_payouts = invalid_payout_result.scalar() or 0
        if invalid_payouts > 0:
            issues.append(f"{invalid_payouts} entries with invalid payout_id")

        if issues:
            return {
                "name": "ledger_references",
                "status": HealthStatus.ERROR,
                "message": "Ledger entries reference non-existent entities",
                "details": {"issues": issues},
            }

        return {
            "name": "ledger_references",
            "status": HealthStatus.OK,
            "message": "All ledger references are valid",
            "details": {},
        }

    async def _check_ledger_math_consistency(self, db: AsyncSession) -> dict:
        """Verify ledger math: payments - refunds should match expected."""
        issues = []

        # Get all bookings with snapshots
        snapshots_result = await db.execute(
            select(BookingFinancialSnapshot)
        )
        snapshots = snapshots_result.scalars().all()

        for snapshot in snapshots:
            # Get payments received for this booking
            payments_result = await db.execute(
                select(func.coalesce(func.sum(SettlementLedgerEntry.amount), 0)).where(
                    SettlementLedgerEntry.booking_id == snapshot.booking_id,
                    SettlementLedgerEntry.entry_type == "payment_received",
                )
            )
            payments_sum = payments_result.scalar() or 0

            # Get refunds issued for this booking
            refunds_result = await db.execute(
                select(func.coalesce(func.sum(SettlementLedgerEntry.amount), 0)).where(
                    SettlementLedgerEntry.booking_id == snapshot.booking_id,
                    SettlementLedgerEntry.entry_type == "refund_issued",
                )
            )
            refunds_sum = refunds_result.scalar() or 0

            # Net should not exceed guest_total
            net_received = payments_sum - refunds_sum
            if net_received > snapshot.guest_total:
                issues.append({
                    "booking_id": str(snapshot.booking_id),
                    "issue": "net_received exceeds guest_total",
                    "net_received": net_received,
                    "guest_total": snapshot.guest_total,
                })

            # Payments should not exceed guest_total
            if payments_sum > snapshot.guest_total:
                issues.append({
                    "booking_id": str(snapshot.booking_id),
                    "issue": "payments exceed guest_total",
                    "payments": payments_sum,
                    "guest_total": snapshot.guest_total,
                })

        if issues:
            return {
                "name": "ledger_math_consistency",
                "status": HealthStatus.ERROR,
                "message": f"{len(issues)} booking(s) have ledger math inconsistencies",
                "details": {"issues": issues[:10]},  # Limit to first 10
            }

        return {
            "name": "ledger_math_consistency",
            "status": HealthStatus.OK,
            "message": "Ledger math is consistent",
            "details": {},
        }

    async def _check_payout_booking_state(self, db: AsyncSession) -> dict:
        """No payout should be released if booking is cancelled or fully refunded."""
        invalid_result = await db.execute(
            select(HostPayout.id, HostPayout.booking_id, Booking.status, Booking.payment_status)
            .join(Booking, HostPayout.booking_id == Booking.id)
            .where(
                HostPayout.status == "released",
                (Booking.status == "cancelled") | (Booking.payment_status == "refunded")
            )
        )
        invalid_payouts = invalid_result.all()

        if invalid_payouts:
            return {
                "name": "payout_booking_state",
                "status": HealthStatus.ERROR,
                "message": f"{len(invalid_payouts)} released payout(s) for cancelled/refunded bookings",
                "details": {
                    "payout_ids": [str(p[0]) for p in invalid_payouts[:10]]
                },
            }

        return {
            "name": "payout_booking_state",
            "status": HealthStatus.OK,
            "message": "No invalid released payouts",
            "details": {},
        }

    async def _check_refund_payment_state(self, db: AsyncSession) -> dict:
        """No refund should exist without a completed payment."""
        invalid_result = await db.execute(
            select(func.count()).select_from(Refund)
            .join(Payment, Refund.payment_id == Payment.id)
            .where(Payment.status != "completed")
        )
        invalid_count = invalid_result.scalar() or 0

        # Also check for refunds exceeding payment amount
        excess_result = await db.execute(
            select(
                Refund.payment_id,
                func.sum(Refund.amount).label("total_refunded"),
                Payment.amount.label("payment_amount")
            )
            .join(Payment, Refund.payment_id == Payment.id)
            .group_by(Refund.payment_id, Payment.amount)
            .having(func.sum(Refund.amount) > Payment.amount)
        )
        excess_refunds = excess_result.all()

        issues = []
        if invalid_count > 0:
            issues.append(f"{invalid_count} refund(s) for non-completed payments")
        if excess_refunds:
            issues.append(f"{len(excess_refunds)} payment(s) with refunds exceeding amount")

        if issues:
            return {
                "name": "refund_payment_state",
                "status": HealthStatus.ERROR,
                "message": "Refund state violations detected",
                "details": {"issues": issues},
            }

        return {
            "name": "refund_payment_state",
            "status": HealthStatus.OK,
            "message": "All refunds have valid payment state",
            "details": {},
        }

    async def _check_ledger_snapshot_requirement(self, db: AsyncSession) -> dict:
        """Payment/refund ledger entries should have corresponding snapshots."""
        # Check payment entries without snapshots
        orphan_result = await db.execute(
            select(func.count()).select_from(SettlementLedgerEntry).where(
                SettlementLedgerEntry.entry_type.in_(["payment_received", "refund_issued"]),
                SettlementLedgerEntry.booking_id.isnot(None),
                ~exists(
                    select(BookingFinancialSnapshot.id).where(
                        BookingFinancialSnapshot.booking_id == SettlementLedgerEntry.booking_id
                    )
                )
            )
        )
        orphan_count = orphan_result.scalar() or 0

        if orphan_count > 0:
            return {
                "name": "ledger_snapshot_requirement",
                "status": HealthStatus.WARNING,
                "message": f"{orphan_count} ledger entries for bookings without snapshots",
                "details": {"count": orphan_count},
            }

        return {
            "name": "ledger_snapshot_requirement",
            "status": HealthStatus.OK,
            "message": "All relevant ledger entries have snapshots",
            "details": {},
        }

    async def _check_orphan_payouts(self, db: AsyncSession) -> dict:
        """Payouts should reference valid bookings."""
        orphan_result = await db.execute(
            select(func.count()).select_from(HostPayout).where(
                HostPayout.booking_id.isnot(None),
                ~exists(
                    select(Booking.id).where(
                        Booking.id == HostPayout.booking_id
                    )
                )
            )
        )
        orphan_count = orphan_result.scalar() or 0

        if orphan_count > 0:
            return {
                "name": "orphan_payouts",
                "status": HealthStatus.ERROR,
                "message": f"{orphan_count} payout(s) reference non-existent bookings",
                "details": {"count": orphan_count},
            }

        return {
            "name": "orphan_payouts",
            "status": HealthStatus.OK,
            "message": "All payouts reference valid bookings",
            "details": {},
        }

    async def _get_counts(self, db: AsyncSession) -> dict:
        """Get entity counts for reporting."""
        bookings = await db.execute(select(func.count()).select_from(Booking))
        snapshots = await db.execute(select(func.count()).select_from(BookingFinancialSnapshot))
        ledger_entries = await db.execute(select(func.count()).select_from(SettlementLedgerEntry))
        payments = await db.execute(select(func.count()).select_from(Payment))
        refunds = await db.execute(select(func.count()).select_from(Refund))
        payouts = await db.execute(select(func.count()).select_from(HostPayout))

        return {
            "bookings": bookings.scalar() or 0,
            "snapshots": snapshots.scalar() or 0,
            "ledger_entries": ledger_entries.scalar() or 0,
            "payments": payments.scalar() or 0,
            "refunds": refunds.scalar() or 0,
            "payouts": payouts.scalar() or 0,
        }


finance_health_service = FinanceHealthService()
