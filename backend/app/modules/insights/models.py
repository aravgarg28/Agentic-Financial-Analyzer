"""Insights module models (T-006 slice): budgets.

Fixes FIN-08/09: monthly budgets keyed by calendar month with a uniqueness
guarantee, in minor units. Recurring series, goals, alerts, etc. arrive in R2.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    ForeignKey,
    Index,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.modules._columns import created_at, deleted_at, id_pk, updated_at


class Budget(Base):
    """Per-category monthly spending target (minor units), calendar-month window."""

    __tablename__ = "budgets"

    id: Mapped[int] = id_pk()
    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), nullable=False
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), nullable=False
    )
    period_month: Mapped[date] = mapped_column(Date, nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rollover: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime | None] = updated_at()
    deleted_at: Mapped[datetime | None] = deleted_at()

    __table_args__ = (
        # One live budget per (household, category, month). Partial so a
        # soft-deleted budget doesn't block re-creating one for the same period.
        Index(
            "uq_budgets_scope_month",
            "household_id",
            "category_id",
            "period_month",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_budgets_household_month", "household_id", "period_month"),
    )
