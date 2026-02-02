"""Internal health and diagnostic endpoints."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_db
from app.models.admin import Dispute
from app.models.financial import SettlementLedgerEntry
from app.models.health import FinanceHealthRun
from app.models.payment import HostPayout
from app.models.user import User
from app.services.finance_health_service import finance_health_service

router = APIRouter()


class HealthCheckResponse(BaseModel):
    """Finance health check response."""

    status: str
    checks: list[dict]
    counts: dict
    timestamp: str


class HealthRunResponse(BaseModel):
    """Persisted health run response."""

    model_config = {"from_attributes": True}

    id: str
    status: str
    trigger: str
    started_at: str
    completed_at: str
    duration_ms: int
    error_message: str | None


@router.get("/health/finance", response_model=HealthCheckResponse)
async def get_finance_health(
    current_user: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> HealthCheckResponse:
    """Run and return finance health check (admin only, read-only)."""
    started_at = datetime.now(UTC)

    result = await finance_health_service.run_all_checks(db)

    completed_at = datetime.now(UTC)
    duration_ms = int((completed_at - started_at).total_seconds() * 1000)

    # Persist the run
    health_run = FinanceHealthRun(
        status=result["status"],
        checks=result["checks"],
        counts=result["counts"],
        trigger="manual",
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=duration_ms,
    )
    db.add(health_run)

    return HealthCheckResponse(**result)


@router.get("/health/finance/history", response_model=list[HealthRunResponse])
async def get_finance_health_history(
    current_user: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 10,
) -> list[HealthRunResponse]:
    """Get recent finance health check runs (admin only)."""
    result = await db.execute(
        select(FinanceHealthRun)
        .order_by(FinanceHealthRun.completed_at.desc())
        .limit(limit)
    )
    runs = result.scalars().all()

    return [
        HealthRunResponse(
            id=str(r.id),
            status=r.status,
            trigger=r.trigger,
            started_at=r.started_at.isoformat(),
            completed_at=r.completed_at.isoformat(),
            duration_ms=r.duration_ms,
            error_message=r.error_message,
        )
        for r in runs
    ]


# ============ SANITY-CHECK ENDPOINTS (READ-ONLY) ============


class SanityCheckResponse(BaseModel):
    """Sanity check response."""

    pending_payouts_count: int
    unreconciled_ledger_count: int
    open_disputes_count: int
    timestamp: str


@router.get("/sanity", response_model=SanityCheckResponse)
async def get_sanity_checks(
    current_user: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SanityCheckResponse:
    """Get system sanity check counts (admin only, read-only)."""
    # Pending payouts count
    pending_payouts_result = await db.execute(
        select(func.count()).select_from(HostPayout).where(
            HostPayout.status.in_(["pending", "eligible"])
        )
    )
    pending_payouts_count = pending_payouts_result.scalar() or 0

    # Unreconciled ledger entries (entries without a reconciliation period link)
    # For simplicity, count entries from today that haven't been aggregated
    unreconciled_result = await db.execute(
        select(func.count()).select_from(SettlementLedgerEntry).where(
            SettlementLedgerEntry.effective_date >= datetime.now(UTC).date()
        )
    )
    unreconciled_ledger_count = unreconciled_result.scalar() or 0

    # Disputes not in terminal states
    terminal_states = ["resolved", "reversed"]
    open_disputes_result = await db.execute(
        select(func.count()).select_from(Dispute).where(
            ~Dispute.status.in_(terminal_states)
        )
    )
    open_disputes_count = open_disputes_result.scalar() or 0

    return SanityCheckResponse(
        pending_payouts_count=pending_payouts_count,
        unreconciled_ledger_count=unreconciled_ledger_count,
        open_disputes_count=open_disputes_count,
        timestamp=datetime.now(UTC).isoformat(),
    )
