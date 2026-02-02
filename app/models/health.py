"""Finance health check persistence models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class FinanceHealthRun(Base):
    """Persisted finance health check results."""

    __tablename__ = "finance_health_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Result
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # OK, WARNING, ERROR
    checks: Mapped[dict] = mapped_column(JSONB, nullable=False)
    counts: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Trigger info
    trigger: Mapped[str] = mapped_column(String(30), nullable=False)  # startup, scheduled, manual

    # Timing
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)

    # Metadata
    error_message: Mapped[str | None] = mapped_column(Text)
