"""Accounting export service for QuickBooks/Xero compatibility."""

import csv
import io
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.financial import BookingFinancialSnapshot, SettlementLedgerEntry
from app.models.payment import HostPayout


class AccountingExportService:
    """Generate accounting-compatible exports."""

    # Account mapping for double-entry bookkeeping
    ACCOUNT_MAPPING = {
        "payment_received": {"debit": "1100-Cash", "credit": "2100-Guest Deposits"},
        "refund_issued": {"debit": "2100-Guest Deposits", "credit": "1100-Cash"},
        "payout_released": {"debit": "2200-Host Payables", "credit": "1100-Cash"},
        "payout_reversed": {"debit": "1100-Cash", "credit": "2200-Host Payables"},
        "dispute_opened": {"debit": "2300-Dispute Reserve", "credit": "2100-Guest Deposits"},
        "dispute_resolved": {"debit": "2100-Guest Deposits", "credit": "2300-Dispute Reserve"},
        "commission_earned": {"debit": "2100-Guest Deposits", "credit": "4100-Commission Revenue"},
    }

    async def export_journal_entries_csv(
        self,
        db: AsyncSession,
        period_start: date,
        period_end: date,
    ) -> str:
        """Export ledger entries as CSV journal entries."""
        entries = await self._get_ledger_entries(db, period_start, period_end)

        output = io.StringIO()
        writer = csv.writer(output)

        # QuickBooks IIF / Xero CSV header
        writer.writerow([
            "Date",
            "Transaction Type",
            "Reference",
            "Description",
            "Account",
            "Debit",
            "Credit",
            "Currency",
        ])

        for entry in entries:
            accounts = self.ACCOUNT_MAPPING.get(entry.entry_type, {})
            amount = entry.amount / 100  # Convert paisa to rupees

            # Debit line
            if accounts.get("debit"):
                writer.writerow([
                    entry.effective_date.isoformat(),
                    entry.entry_type.upper(),
                    str(entry.id)[:8],
                    entry.description or entry.entry_type,
                    accounts["debit"],
                    f"{amount:.2f}",
                    "",
                    entry.currency,
                ])

            # Credit line
            if accounts.get("credit"):
                writer.writerow([
                    entry.effective_date.isoformat(),
                    entry.entry_type.upper(),
                    str(entry.id)[:8],
                    entry.description or entry.entry_type,
                    accounts["credit"],
                    "",
                    f"{amount:.2f}",
                    entry.currency,
                ])

        return output.getvalue()

    async def export_journal_entries_json(
        self,
        db: AsyncSession,
        period_start: date,
        period_end: date,
    ) -> str:
        """Export ledger entries as JSON journal entries."""
        entries = await self._get_ledger_entries(db, period_start, period_end)

        journals = []
        for entry in entries:
            accounts = self.ACCOUNT_MAPPING.get(entry.entry_type, {})
            amount = entry.amount / 100

            journal = {
                "date": entry.effective_date.isoformat(),
                "reference": str(entry.id),
                "narration": entry.description or entry.entry_type,
                "currency": entry.currency,
                "lines": [],
            }

            if accounts.get("debit"):
                journal["lines"].append({
                    "account": accounts["debit"],
                    "debit": amount,
                    "credit": 0,
                })

            if accounts.get("credit"):
                journal["lines"].append({
                    "account": accounts["credit"],
                    "debit": 0,
                    "credit": amount,
                })

            journals.append(journal)

        return json.dumps({"journals": journals}, indent=2, default=str)

    async def export_payouts_csv(
        self,
        db: AsyncSession,
        period_start: date,
        period_end: date,
    ) -> str:
        """Export payouts as CSV for accounts payable."""
        payouts = await self._get_payouts(db, period_start, period_end)

        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow([
            "Payout ID",
            "Host ID",
            "Booking ID",
            "Amount",
            "Currency",
            "Status",
            "Method",
            "Payout Date",
            "Processed Date",
            "Created Date",
        ])

        for payout in payouts:
            writer.writerow([
                str(payout.id),
                str(payout.host_id),
                str(payout.booking_id) if payout.booking_id else "",
                f"{payout.amount / 100:.2f}",
                payout.currency,
                payout.status,
                payout.payout_method or "",
                payout.payout_date.isoformat(),
                payout.processed_at.isoformat() if payout.processed_at else "",
                payout.created_at.isoformat(),
            ])

        return output.getvalue()

    async def export_payouts_json(
        self,
        db: AsyncSession,
        period_start: date,
        period_end: date,
    ) -> str:
        """Export payouts as JSON."""
        payouts = await self._get_payouts(db, period_start, period_end)

        data = [
            {
                "payout_id": str(p.id),
                "host_id": str(p.host_id),
                "booking_id": str(p.booking_id) if p.booking_id else None,
                "amount": p.amount / 100,
                "currency": p.currency,
                "status": p.status,
                "method": p.payout_method,
                "payout_date": p.payout_date.isoformat(),
                "processed_at": p.processed_at.isoformat() if p.processed_at else None,
                "created_at": p.created_at.isoformat(),
            }
            for p in payouts
        ]

        return json.dumps({"payouts": data}, indent=2)

    async def export_commissions_csv(
        self,
        db: AsyncSession,
        period_start: date,
        period_end: date,
    ) -> str:
        """Export commission revenue as CSV."""
        snapshots = await self._get_snapshots(db, period_start, period_end)

        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow([
            "Booking ID",
            "Booking Number",
            "Date",
            "Guest Total",
            "Commission Rate",
            "Commission Amount",
            "Host Payout",
            "Source",
            "Currency",
        ])

        for snap in snapshots:
            writer.writerow([
                str(snap.booking_id),
                snap.booking_number,
                snap.snapshot_at.date().isoformat(),
                f"{snap.guest_total / 100:.2f}",
                f"{snap.commission_rate:.2f}%",
                f"{snap.commission_amount / 100:.2f}",
                f"{snap.host_payout_amount / 100:.2f}",
                snap.source,
                snap.currency,
            ])

        return output.getvalue()

    async def export_commissions_json(
        self,
        db: AsyncSession,
        period_start: date,
        period_end: date,
    ) -> str:
        """Export commission revenue as JSON."""
        snapshots = await self._get_snapshots(db, period_start, period_end)

        data = [
            {
                "booking_id": str(s.booking_id),
                "booking_number": s.booking_number,
                "date": s.snapshot_at.date().isoformat(),
                "guest_total": s.guest_total / 100,
                "commission_rate": float(s.commission_rate),
                "commission_amount": s.commission_amount / 100,
                "host_payout": s.host_payout_amount / 100,
                "source": s.source,
                "currency": s.currency,
            }
            for s in snapshots
        ]

        return json.dumps({"commissions": data}, indent=2)

    async def export_summary_json(
        self,
        db: AsyncSession,
        period_start: date,
        period_end: date,
    ) -> str:
        """Export period summary as JSON."""
        # Ledger totals
        ledger_result = await db.execute(
            select(
                SettlementLedgerEntry.entry_type,
                func.sum(SettlementLedgerEntry.amount),
                func.count(),
            )
            .where(
                SettlementLedgerEntry.effective_date >= period_start,
                SettlementLedgerEntry.effective_date <= period_end,
            )
            .group_by(SettlementLedgerEntry.entry_type)
        )
        ledger_totals = {row[0]: {"amount": row[1] / 100, "count": row[2]} for row in ledger_result.all()}

        # Commission totals
        commission_result = await db.execute(
            select(
                func.sum(BookingFinancialSnapshot.guest_total),
                func.sum(BookingFinancialSnapshot.commission_amount),
                func.count(),
            ).where(
                func.date(BookingFinancialSnapshot.snapshot_at) >= period_start,
                func.date(BookingFinancialSnapshot.snapshot_at) <= period_end,
            )
        )
        guest_total, commission_total, booking_count = commission_result.one()

        summary = {
            "period": {
                "start": period_start.isoformat(),
                "end": period_end.isoformat(),
            },
            "ledger_totals": ledger_totals,
            "revenue": {
                "gross_booking_value": (guest_total or 0) / 100,
                "commission_earned": (commission_total or 0) / 100,
                "booking_count": booking_count or 0,
            },
            "currency": "PKR",
            "generated_at": datetime.utcnow().isoformat(),
        }

        return json.dumps(summary, indent=2)

    async def _get_ledger_entries(
        self,
        db: AsyncSession,
        period_start: date,
        period_end: date,
    ) -> list[SettlementLedgerEntry]:
        """Get ledger entries for period."""
        result = await db.execute(
            select(SettlementLedgerEntry)
            .where(
                SettlementLedgerEntry.effective_date >= period_start,
                SettlementLedgerEntry.effective_date <= period_end,
            )
            .order_by(SettlementLedgerEntry.created_at)
        )
        return list(result.scalars().all())

    async def _get_payouts(
        self,
        db: AsyncSession,
        period_start: date,
        period_end: date,
    ) -> list[HostPayout]:
        """Get payouts for period."""
        result = await db.execute(
            select(HostPayout)
            .where(
                HostPayout.payout_date >= period_start,
                HostPayout.payout_date <= period_end,
            )
            .order_by(HostPayout.created_at)
        )
        return list(result.scalars().all())

    async def _get_snapshots(
        self,
        db: AsyncSession,
        period_start: date,
        period_end: date,
    ) -> list[BookingFinancialSnapshot]:
        """Get snapshots for period."""
        result = await db.execute(
            select(BookingFinancialSnapshot)
            .where(
                func.date(BookingFinancialSnapshot.snapshot_at) >= period_start,
                func.date(BookingFinancialSnapshot.snapshot_at) <= period_end,
            )
            .order_by(BookingFinancialSnapshot.snapshot_at)
        )
        return list(result.scalars().all())


accounting_export_service = AccountingExportService()
