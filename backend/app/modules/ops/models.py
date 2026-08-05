"""Ops module models (T-006): background job queue table.

The table is created now so migrations stay linear; the worker that consumes it
is bootstrapped in R2 (ADR-05). Consumed via SELECT ... FOR UPDATE SKIP LOCKED.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.modules._columns import created_at, id_pk, updated_at


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = id_pk()
    type: Mapped[str] = mapped_column(String(48), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="queued")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    run_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime | None] = updated_at()

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed')", name="ck_jobs_status"
        ),
        Index(
            "ix_jobs_queued",
            "status",
            "run_after",
            postgresql_where=text("status = 'queued'"),
        ),
    )
