"""Reusable column factories for consistent PKs, ids, and timestamps.

Each factory returns a fresh ``mapped_column`` on every call, so the same helper
can be used across many models. Money is always integer minor units elsewhere;
these helpers cover the non-money boilerplate.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


def id_pk() -> Mapped[int]:
    return mapped_column(BigInteger, primary_key=True, autoincrement=True)


def public_uuid() -> Mapped[str]:
    """External-facing opaque id (UUID) so integer PKs never leak/enumerate."""
    return mapped_column(
        UUID(as_uuid=False),
        server_default=text("gen_random_uuid()"),
        unique=True,
        nullable=False,
    )


def created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def updated_at() -> Mapped[datetime | None]:
    return mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
    )


def deleted_at() -> Mapped[datetime | None]:
    return mapped_column(DateTime(timezone=True), nullable=True)
