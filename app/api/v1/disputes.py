"""Dispute and chargeback endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_current_admin, get_db
from app.core.exceptions import NotFoundError
from app.models.admin import Dispute
from app.models.user import User
from app.services.dispute_service import dispute_service

router = APIRouter()


# ============ SCHEMAS ============


class DisputeCreate(BaseModel):
    """Schema for opening a dispute."""

    booking_id: UUID
    against_id: UUID
    category: str = Field(..., pattern="^(property_issue|host_issue|guest_issue|payment|chargeback|other)$")
    description: str = Field(..., min_length=20, max_length=5000)
    evidence_urls: list[str] | None = None


class DisputeResolve(BaseModel):
    """Schema for resolving a dispute."""

    resolution: str = Field(..., min_length=10, max_length=5000)
    resolution_type: str = Field(..., pattern="^(refund|payout_reversal|no_action|chargeback_won|chargeback_lost)$")
    refund_amount: int = Field(default=0, ge=0)
    payout_adjustment: int = Field(default=0, ge=0)


class DisputeReverse(BaseModel):
    """Schema for reversing a dispute resolution."""

    reason: str = Field(..., min_length=10, max_length=2000)


class DisputeResponse(BaseModel):
    """Schema for dispute response."""

    model_config = {"from_attributes": True}

    id: UUID
    booking_id: UUID
    raised_by: UUID
    against_id: UUID
    category: str
    description: str
    evidence_urls: list[str] | None
    status: str
    resolution: str | None
    resolution_type: str | None
    refund_granted: int
    payout_adjusted: int
    assigned_to: UUID | None
    resolved_by: UUID | None
    resolved_at: str | None
    created_at: str


# ============ ENDPOINTS ============


@router.post("/", response_model=DisputeResponse, status_code=status.HTTP_201_CREATED)
async def open_dispute(
    data: DisputeCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Dispute:
    """Open a new dispute."""
    dispute = await dispute_service.open_dispute(
        db=db,
        booking_id=data.booking_id,
        raised_by=current_user.id,
        against_id=data.against_id,
        category=data.category,
        description=data.description,
        evidence_urls=data.evidence_urls,
    )
    return dispute


@router.get("/{dispute_id}", response_model=DisputeResponse)
async def get_dispute(
    dispute_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Dispute:
    """Get dispute details."""
    result = await db.execute(select(Dispute).where(Dispute.id == dispute_id))
    dispute = result.scalar_one_or_none()
    if not dispute:
        raise NotFoundError("Dispute", str(dispute_id))

    # Check access: must be raiser, against, or admin
    if current_user.role != "admin" and current_user.id not in (dispute.raised_by, dispute.against_id):
        raise NotFoundError("Dispute", str(dispute_id))

    return dispute


@router.post("/{dispute_id}/review", response_model=DisputeResponse)
async def start_dispute_review(
    dispute_id: UUID,
    current_user: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Dispute:
    """Start reviewing a dispute (admin only)."""
    dispute = await dispute_service.start_review(
        db=db,
        dispute_id=dispute_id,
        assigned_to=current_user.id,
    )
    return dispute


@router.post("/{dispute_id}/resolve", response_model=DisputeResponse)
async def resolve_dispute(
    dispute_id: UUID,
    data: DisputeResolve,
    current_user: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Dispute:
    """Resolve a dispute (admin only)."""
    dispute = await dispute_service.resolve_dispute(
        db=db,
        dispute_id=dispute_id,
        resolved_by=current_user.id,
        resolution=data.resolution,
        resolution_type=data.resolution_type,
        refund_amount=data.refund_amount,
        payout_adjustment=data.payout_adjustment,
    )
    return dispute


@router.post("/{dispute_id}/reverse", response_model=DisputeResponse)
async def reverse_dispute_resolution(
    dispute_id: UUID,
    data: DisputeReverse,
    current_user: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Dispute:
    """Reverse a dispute resolution (admin only)."""
    dispute = await dispute_service.reverse_resolution(
        db=db,
        dispute_id=dispute_id,
        reversed_by=current_user.id,
        reason=data.reason,
    )
    return dispute
