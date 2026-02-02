"""Financial reporting service (read-only queries)."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.financial import (
    BookingFinancialSnapshot,
    SettlementLedgerEntry,
)
from app.models.payment import HostPayout
from app.models.user import User


class ReportingService:
    """Read-only financial reporting service."""

    async def get_daily_settlement_summary(
        self,
        db: AsyncSession,
        report_date: date,
    ) -> dict:
        """Get daily settlement summary from ledger entries."""
        # Payments received
        payments = await db.execute(
            select(
                func.coalesce(func.sum(SettlementLedgerEntry.amount), 0),
                func.count(),
            ).where(
                SettlementLedgerEntry.entry_type == "payment_received",
                SettlementLedgerEntry.effective_date == report_date,
            )
        )
        payments_sum, payments_count = payments.one()

        # Refunds issued
        refunds = await db.execute(
            select(
                func.coalesce(func.sum(SettlementLedgerEntry.amount), 0),
                func.count(),
            ).where(
                SettlementLedgerEntry.entry_type == "refund_issued",
                SettlementLedgerEntry.effective_date == report_date,
            )
        )
        refunds_sum, refunds_count = refunds.one()

        # Payouts released
        payouts = await db.execute(
            select(
                func.coalesce(func.sum(SettlementLedgerEntry.amount), 0),
                func.count(),
            ).where(
                SettlementLedgerEntry.entry_type == "payout_released",
                SettlementLedgerEntry.effective_date == report_date,
            )
        )
        payouts_sum, payouts_count = payouts.one()

        # Payouts reversed
        reversals = await db.execute(
            select(
                func.coalesce(func.sum(SettlementLedgerEntry.amount), 0),
                func.count(),
            ).where(
                SettlementLedgerEntry.entry_type == "payout_reversed",
                SettlementLedgerEntry.effective_date == report_date,
            )
        )
        reversals_sum, reversals_count = reversals.one()

        net_position = payments_sum - refunds_sum - payouts_sum + reversals_sum

        return {
            "report_date": report_date,
            "total_payments_received": payments_sum,
            "total_refunds_issued": refunds_sum,
            "total_payouts_released": payouts_sum,
            "total_payouts_reversed": reversals_sum,
            "net_position": net_position,
            "payment_count": payments_count,
            "refund_count": refunds_count,
            "payout_count": payouts_count,
            "reversal_count": reversals_count,
            "currency": "PKR",
        }

    async def get_monthly_settlement_summary(
        self,
        db: AsyncSession,
        year: int,
        month: int,
    ) -> dict:
        """Get monthly settlement summary."""
        from calendar import monthrange

        period_start = date(year, month, 1)
        _, last_day = monthrange(year, month)
        period_end = date(year, month, last_day)

        # Payments received
        payments = await db.execute(
            select(
                func.coalesce(func.sum(SettlementLedgerEntry.amount), 0),
                func.count(),
            ).where(
                SettlementLedgerEntry.entry_type == "payment_received",
                SettlementLedgerEntry.effective_date >= period_start,
                SettlementLedgerEntry.effective_date <= period_end,
            )
        )
        payments_sum, payments_count = payments.one()

        # Refunds issued
        refunds = await db.execute(
            select(
                func.coalesce(func.sum(SettlementLedgerEntry.amount), 0),
                func.count(),
            ).where(
                SettlementLedgerEntry.entry_type == "refund_issued",
                SettlementLedgerEntry.effective_date >= period_start,
                SettlementLedgerEntry.effective_date <= period_end,
            )
        )
        refunds_sum, refunds_count = refunds.one()

        # Payouts released
        payouts = await db.execute(
            select(
                func.coalesce(func.sum(SettlementLedgerEntry.amount), 0),
                func.count(),
            ).where(
                SettlementLedgerEntry.entry_type == "payout_released",
                SettlementLedgerEntry.effective_date >= period_start,
                SettlementLedgerEntry.effective_date <= period_end,
            )
        )
        payouts_sum, payouts_count = payouts.one()

        # Payouts reversed
        reversals = await db.execute(
            select(
                func.coalesce(func.sum(SettlementLedgerEntry.amount), 0),
                func.count(),
            ).where(
                SettlementLedgerEntry.entry_type == "payout_reversed",
                SettlementLedgerEntry.effective_date >= period_start,
                SettlementLedgerEntry.effective_date <= period_end,
            )
        )
        reversals_sum, _ = reversals.one()

        # Commission from snapshots
        commission = await db.execute(
            select(
                func.coalesce(func.sum(BookingFinancialSnapshot.commission_amount), 0),
                func.count(),
            ).where(
                func.date(BookingFinancialSnapshot.snapshot_at) >= period_start,
                func.date(BookingFinancialSnapshot.snapshot_at) <= period_end,
            )
        )
        commission_sum, booking_count = commission.one()

        net_position = payments_sum - refunds_sum - payouts_sum + reversals_sum

        return {
            "year": year,
            "month": month,
            "period_start": period_start,
            "period_end": period_end,
            "total_payments_received": payments_sum,
            "total_refunds_issued": refunds_sum,
            "total_payouts_released": payouts_sum,
            "total_payouts_reversed": reversals_sum,
            "net_position": net_position,
            "total_commission_earned": commission_sum,
            "payment_count": payments_count,
            "refund_count": refunds_count,
            "payout_count": payouts_count,
            "booking_count": booking_count,
            "currency": "PKR",
        }

    async def get_host_earnings_statement(
        self,
        db: AsyncSession,
        host_id: UUID,
        period_start: date,
        period_end: date,
    ) -> dict:
        """Get host earnings statement for a date range."""
        # Get host info
        user_result = await db.execute(select(User).where(User.id == host_id))
        user = user_result.scalar_one_or_none()
        host_email = user.email if user else "unknown"

        # Get snapshots for host in period
        snapshots = await db.execute(
            select(
                func.count(),
                func.coalesce(func.sum(BookingFinancialSnapshot.nights), 0),
                func.coalesce(func.sum(BookingFinancialSnapshot.guest_total), 0),
                func.coalesce(func.sum(BookingFinancialSnapshot.commission_amount), 0),
                func.coalesce(func.sum(BookingFinancialSnapshot.host_payout_amount), 0),
            ).where(
                BookingFinancialSnapshot.host_id == host_id,
                func.date(BookingFinancialSnapshot.snapshot_at) >= period_start,
                func.date(BookingFinancialSnapshot.snapshot_at) <= period_end,
            )
        )
        booking_count, total_nights, gross, commission, host_payout = snapshots.one()

        # Get refunds for host's bookings in period
        refunds = await db.execute(
            select(func.coalesce(func.sum(SettlementLedgerEntry.amount), 0)).where(
                SettlementLedgerEntry.entry_type == "refund_issued",
                SettlementLedgerEntry.effective_date >= period_start,
                SettlementLedgerEntry.effective_date <= period_end,
                SettlementLedgerEntry.booking_id.in_(
                    select(BookingFinancialSnapshot.booking_id).where(
                        BookingFinancialSnapshot.host_id == host_id
                    )
                ),
            )
        )
        refunds_sum = refunds.scalar() or 0

        # Get payouts released
        released = await db.execute(
            select(func.coalesce(func.sum(HostPayout.amount), 0)).where(
                HostPayout.host_id == host_id,
                HostPayout.status == "released",
                HostPayout.payout_date >= period_start,
                HostPayout.payout_date <= period_end,
            )
        )
        released_sum = released.scalar() or 0

        # Get payouts pending
        pending = await db.execute(
            select(func.coalesce(func.sum(HostPayout.amount), 0)).where(
                HostPayout.host_id == host_id,
                HostPayout.status.in_(["pending", "eligible"]),
            )
        )
        pending_sum = pending.scalar() or 0

        net_earnings = host_payout - refunds_sum

        return {
            "host_id": host_id,
            "host_email": host_email,
            "period_start": period_start,
            "period_end": period_end,
            "total_bookings": booking_count,
            "total_nights": total_nights,
            "gross_earnings": gross,
            "commission_paid": commission,
            "refunds_deducted": refunds_sum,
            "net_earnings": net_earnings,
            "payouts_released": released_sum,
            "payouts_pending": pending_sum,
            "currency": "PKR",
        }

    async def get_host_earnings_line_items(
        self,
        db: AsyncSession,
        host_id: UUID,
        period_start: date,
        period_end: date,
    ) -> list:
        """Get individual booking line items for host earnings."""
        from app.models.booking import Booking

        result = await db.execute(
            select(BookingFinancialSnapshot)
            .where(
                BookingFinancialSnapshot.host_id == host_id,
                func.date(BookingFinancialSnapshot.snapshot_at) >= period_start,
                func.date(BookingFinancialSnapshot.snapshot_at) <= period_end,
            )
            .order_by(BookingFinancialSnapshot.snapshot_at.desc())
        )
        snapshots = result.scalars().all()

        items = []
        for snap in snapshots:
            # Get refund amount for this booking
            refund_result = await db.execute(
                select(func.coalesce(func.sum(SettlementLedgerEntry.amount), 0)).where(
                    SettlementLedgerEntry.entry_type == "refund_issued",
                    SettlementLedgerEntry.booking_id == snap.booking_id,
                )
            )
            refund_amount = refund_result.scalar() or 0

            items.append({
                "booking_id": snap.booking_id,
                "booking_number": snap.booking_number,
                "check_in": snap.check_in,
                "check_out": snap.check_out,
                "nights": snap.nights,
                "guest_total": snap.guest_total,
                "commission_rate": snap.commission_rate,
                "commission_amount": snap.commission_amount,
                "host_payout_amount": snap.host_payout_amount,
                "refund_amount": refund_amount,
                "snapshot_at": snap.snapshot_at,
            })

        return items

    async def get_platform_revenue_report(
        self,
        db: AsyncSession,
        period_start: date,
        period_end: date,
    ) -> dict:
        """Get platform commission revenue report."""
        # Total commission from snapshots
        result = await db.execute(
            select(
                func.coalesce(func.sum(BookingFinancialSnapshot.guest_total), 0),
                func.coalesce(func.sum(BookingFinancialSnapshot.commission_amount), 0),
                func.count(),
            ).where(
                func.date(BookingFinancialSnapshot.snapshot_at) >= period_start,
                func.date(BookingFinancialSnapshot.snapshot_at) <= period_end,
            )
        )
        total_value, total_commission, booking_count = result.one()

        # Average commission rate
        avg_rate = Decimal("0.00")
        if total_value > 0:
            avg_rate = (Decimal(total_commission) / Decimal(total_value) * 100).quantize(
                Decimal("0.01")
            )

        # Commission by source
        by_source_result = await db.execute(
            select(
                BookingFinancialSnapshot.source,
                func.sum(BookingFinancialSnapshot.commission_amount),
            )
            .where(
                func.date(BookingFinancialSnapshot.snapshot_at) >= period_start,
                func.date(BookingFinancialSnapshot.snapshot_at) <= period_end,
            )
            .group_by(BookingFinancialSnapshot.source)
        )
        by_source = {row[0]: row[1] for row in by_source_result.all()}

        return {
            "period_start": period_start,
            "period_end": period_end,
            "total_booking_value": total_value,
            "total_commission_earned": total_commission,
            "average_commission_rate": avg_rate,
            "booking_count": booking_count,
            "by_source": by_source,
            "currency": "PKR",
        }

    async def get_ledger_entries_export(
        self,
        db: AsyncSession,
        period_start: date,
        period_end: date,
    ) -> list:
        """Get ledger entries for export."""
        result = await db.execute(
            select(SettlementLedgerEntry)
            .where(
                SettlementLedgerEntry.effective_date >= period_start,
                SettlementLedgerEntry.effective_date <= period_end,
            )
            .order_by(SettlementLedgerEntry.created_at)
        )
        return list(result.scalars().all())

    async def get_payouts_export(
        self,
        db: AsyncSession,
        period_start: date,
        period_end: date,
        status_filter: str | None = None,
    ) -> list:
        """Get payouts for export."""
        query = select(HostPayout).where(
            HostPayout.payout_date >= period_start,
            HostPayout.payout_date <= period_end,
        )
        if status_filter:
            query = query.where(HostPayout.status == status_filter)
        query = query.order_by(HostPayout.created_at)

        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_commissions_export(
        self,
        db: AsyncSession,
        period_start: date,
        period_end: date,
    ) -> list:
        """Get commission records for export."""
        result = await db.execute(
            select(BookingFinancialSnapshot)
            .where(
                func.date(BookingFinancialSnapshot.snapshot_at) >= period_start,
                func.date(BookingFinancialSnapshot.snapshot_at) <= period_end,
            )
            .order_by(BookingFinancialSnapshot.snapshot_at)
        )
        snapshots = result.scalars().all()

        return [
            {
                "booking_id": s.booking_id,
                "booking_number": s.booking_number,
                "guest_total": s.guest_total,
                "commission_rate": s.commission_rate,
                "commission_amount": s.commission_amount,
                "host_payout_amount": s.host_payout_amount,
                "source": s.source,
                "snapshot_at": s.snapshot_at,
                "currency": s.currency,
            }
            for s in snapshots
        ]


reporting_service = ReportingService()
