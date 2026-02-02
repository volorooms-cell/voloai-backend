"""Financial reporting endpoints (read-only)."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_current_host, get_db
from app.models.user import User
from app.schemas.reporting import (
    CommissionExport,
    DailySettlementSummary,
    HostEarningsDetail,
    HostEarningsLineItem,
    HostEarningsStatement,
    LedgerEntryExport,
    MonthlySettlementSummary,
    PayoutExport,
    PlatformRevenueReport,
)
from app.services.accounting_export_service import accounting_export_service
from app.services.reporting_service import reporting_service

router = APIRouter()


# ============ PLATFORM REPORTS (Admin Only) ============


@router.get("/settlement/daily", response_model=DailySettlementSummary)
async def get_daily_settlement(
    current_user: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    report_date: date = Query(default_factory=date.today),
) -> DailySettlementSummary:
    """Get daily settlement summary (admin only)."""
    data = await reporting_service.get_daily_settlement_summary(db, report_date)
    return DailySettlementSummary(**data)


@router.get("/settlement/monthly", response_model=MonthlySettlementSummary)
async def get_monthly_settlement(
    current_user: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
) -> MonthlySettlementSummary:
    """Get monthly settlement summary (admin only)."""
    data = await reporting_service.get_monthly_settlement_summary(db, year, month)
    return MonthlySettlementSummary(**data)


@router.get("/revenue", response_model=PlatformRevenueReport)
async def get_platform_revenue(
    current_user: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    period_start: date = Query(...),
    period_end: date = Query(...),
) -> PlatformRevenueReport:
    """Get platform commission revenue report (admin only)."""
    data = await reporting_service.get_platform_revenue_report(db, period_start, period_end)
    return PlatformRevenueReport(**data)


# ============ HOST EARNINGS ============


@router.get("/host/earnings", response_model=HostEarningsStatement)
async def get_my_earnings(
    current_user: Annotated[User, Depends(get_current_host)],
    db: Annotated[AsyncSession, Depends(get_db)],
    period_start: date = Query(...),
    period_end: date = Query(...),
) -> HostEarningsStatement:
    """Get current host's earnings statement."""
    data = await reporting_service.get_host_earnings_statement(
        db, current_user.id, period_start, period_end
    )
    return HostEarningsStatement(**data)


@router.get("/host/earnings/detail", response_model=HostEarningsDetail)
async def get_my_earnings_detail(
    current_user: Annotated[User, Depends(get_current_host)],
    db: Annotated[AsyncSession, Depends(get_db)],
    period_start: date = Query(...),
    period_end: date = Query(...),
) -> HostEarningsDetail:
    """Get current host's earnings with line items."""
    summary = await reporting_service.get_host_earnings_statement(
        db, current_user.id, period_start, period_end
    )
    line_items = await reporting_service.get_host_earnings_line_items(
        db, current_user.id, period_start, period_end
    )
    return HostEarningsDetail(
        summary=HostEarningsStatement(**summary),
        line_items=[HostEarningsLineItem(**item) for item in line_items],
    )


@router.get("/host/{host_id}/earnings", response_model=HostEarningsStatement)
async def get_host_earnings(
    host_id: UUID,
    current_user: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    period_start: date = Query(...),
    period_end: date = Query(...),
) -> HostEarningsStatement:
    """Get specific host's earnings statement (admin only)."""
    data = await reporting_service.get_host_earnings_statement(
        db, host_id, period_start, period_end
    )
    return HostEarningsStatement(**data)


# ============ EXPORTS ============


@router.get("/export/ledger", response_model=list[LedgerEntryExport])
async def export_ledger_entries(
    current_user: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    period_start: date = Query(...),
    period_end: date = Query(...),
) -> list[LedgerEntryExport]:
    """Export ledger entries for accounting (admin only)."""
    entries = await reporting_service.get_ledger_entries_export(db, period_start, period_end)
    return [LedgerEntryExport.model_validate(e) for e in entries]


@router.get("/export/payouts", response_model=list[PayoutExport])
async def export_payouts(
    current_user: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    period_start: date = Query(...),
    period_end: date = Query(...),
    status: str | None = Query(default=None),
) -> list[PayoutExport]:
    """Export payouts for accounting (admin only)."""
    payouts = await reporting_service.get_payouts_export(db, period_start, period_end, status)
    return [PayoutExport.model_validate(p) for p in payouts]


@router.get("/export/commissions", response_model=list[CommissionExport])
async def export_commissions(
    current_user: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    period_start: date = Query(...),
    period_end: date = Query(...),
) -> list[CommissionExport]:
    """Export commission records for accounting (admin only)."""
    commissions = await reporting_service.get_commissions_export(db, period_start, period_end)
    return [CommissionExport(**c) for c in commissions]


# ============ ACCOUNTING EXPORTS (QuickBooks/Xero Compatible) ============


from fastapi.responses import PlainTextResponse


@router.get("/accounting/journal.csv")
async def export_journal_csv(
    current_user: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    period_start: date = Query(...),
    period_end: date = Query(...),
) -> PlainTextResponse:
    """Export journal entries as CSV (QuickBooks/Xero compatible)."""
    csv_data = await accounting_export_service.export_journal_entries_csv(
        db, period_start, period_end
    )
    return PlainTextResponse(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=journal_{period_start}_{period_end}.csv"},
    )


@router.get("/accounting/journal.json")
async def export_journal_json(
    current_user: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    period_start: date = Query(...),
    period_end: date = Query(...),
) -> PlainTextResponse:
    """Export journal entries as JSON."""
    json_data = await accounting_export_service.export_journal_entries_json(
        db, period_start, period_end
    )
    return PlainTextResponse(
        content=json_data,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=journal_{period_start}_{period_end}.json"},
    )


@router.get("/accounting/payouts.csv")
async def export_payouts_csv(
    current_user: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    period_start: date = Query(...),
    period_end: date = Query(...),
) -> PlainTextResponse:
    """Export payouts as CSV."""
    csv_data = await accounting_export_service.export_payouts_csv(
        db, period_start, period_end
    )
    return PlainTextResponse(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=payouts_{period_start}_{period_end}.csv"},
    )


@router.get("/accounting/commissions.csv")
async def export_commissions_csv(
    current_user: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    period_start: date = Query(...),
    period_end: date = Query(...),
) -> PlainTextResponse:
    """Export commission revenue as CSV."""
    csv_data = await accounting_export_service.export_commissions_csv(
        db, period_start, period_end
    )
    return PlainTextResponse(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=commissions_{period_start}_{period_end}.csv"},
    )


@router.get("/accounting/summary.json")
async def export_period_summary(
    current_user: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    period_start: date = Query(...),
    period_end: date = Query(...),
) -> PlainTextResponse:
    """Export period summary as JSON."""
    json_data = await accounting_export_service.export_summary_json(
        db, period_start, period_end
    )
    return PlainTextResponse(
        content=json_data,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=summary_{period_start}_{period_end}.json"},
    )
