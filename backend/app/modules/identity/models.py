"""Identity module models (T-006): households, users, memberships, sessions,
audit events. Tenant root is the household; every domain row scopes to it.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.modules._columns import created_at, deleted_at, id_pk, public_uuid


class Household(Base):
    """Tenant root. Owns timezone and base currency (drives month boundaries)."""

    __tablename__ = "households"

    id: Mapped[int] = id_pk()
    public_id: Mapped[str] = public_uuid()
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="USD")
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default="America/New_York"
    )
    created_at: Mapped[datetime] = created_at()
    deleted_at: Mapped[datetime | None] = deleted_at()


class User(Base):
    """A login identity. Reaches data only through a membership → household."""

    __tablename__ = "users"

    id: Mapped[int] = id_pk()
    public_id: Mapped[str] = public_uuid()
    email: Mapped[str] = mapped_column(CITEXT(), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    password_algo: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="argon2id"
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    failed_login_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = created_at()
    deleted_at: Mapped[datetime | None] = deleted_at()

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'disabled')", name="ck_users_status"
        ),
    )


class Membership(Base):
    """Links a user to a household with a role. Beta: one owner per household."""

    __tablename__ = "memberships"

    id: Mapped[int] = id_pk()
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = created_at()

    __table_args__ = (
        UniqueConstraint("user_id", "household_id", name="uq_membership_user_household"),
        CheckConstraint(
            "role IN ('owner', 'member', 'viewer')", name="ck_membership_role"
        ),
        Index("ix_memberships_household", "household_id"),
        Index("ix_memberships_user", "user_id"),
    )


class AuthSession(Base):
    """Server-side session. Stores only the token hash; the opaque token itself
    lives only in the client cookie. Source of truth for the request Principal.
    """

    __tablename__ = "sessions"

    id: Mapped[int] = id_pk()
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = created_at()
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_sessions_user", "user_id"),)


class AuditEvent(Base):
    """Append-only record of security/financial-relevant actions (INF-06)."""

    __tablename__ = "audit_events"

    id: Mapped[int] = id_pk()
    household_id: Mapped[int | None] = mapped_column(
        ForeignKey("households.id", ondelete="SET NULL"), nullable=True
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_public_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 'metadata' is reserved on the Declarative Base, so the column is named
    # event_metadata. No secrets or full financial payloads belong here.
    event_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = created_at()

    __table_args__ = (
        Index("ix_audit_household_created", "household_id", "created_at"),
        Index("ix_audit_action", "action"),
    )
