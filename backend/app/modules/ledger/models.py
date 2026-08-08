"""Ledger module models (T-006 slice): accounts, categories, transactions.

Money is integer minor units (``*_minor`` BIGINT) plus an ISO-4217 currency.
FK columns whose target tables arrive in later releases (merchants, transfers,
recurring series, import batches, connections) are intentionally omitted here
and added by additive migrations when those tables exist (migration-plan §4).
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.modules._columns import created_at, deleted_at, id_pk, public_uuid, updated_at

_ACCOUNT_TYPES = "'checking', 'savings', 'credit_card', 'loan', 'investment', 'property', 'cash', 'other'"


class Institution(Base):
    """A user-labeled financial institution (T-060). connection_id / aggregator
    linkage arrives in R2; for now this is a simple household-scoped label that
    accounts and (later) saved CSV mappings hang off of."""

    __tablename__ = "institutions"

    id: Mapped[int] = id_pk()
    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), nullable=False
    )
    public_id: Mapped[str] = public_uuid()
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # kind is a free label (e.g. 'bank', 'credit_union', 'card_issuer'); not a
    # closed enum because users name their own institutions.
    kind: Mapped[str | None] = mapped_column(String(40), nullable=True)
    logo_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    aggregator_institution_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = created_at()
    deleted_at: Mapped[datetime | None] = deleted_at()

    __table_args__ = (
        Index("ix_institutions_household", "household_id"),
        UniqueConstraint("household_id", "name", name="uq_institutions_scope_name"),
    )


class Account(Base):
    """A bank/credit account (full transactions) or a balance-only container.

    connection_id (aggregator link) is added in R2 when that table lands.
    """

    __tablename__ = "accounts"

    id: Mapped[int] = id_pk()
    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), nullable=False
    )
    institution_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "institutions.id", ondelete="SET NULL", name="fk_accounts_institution_id"
        ),
        nullable=True,
    )
    public_id: Mapped[str] = public_uuid()
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    tracking_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    current_balance_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = created_at()
    deleted_at: Mapped[datetime | None] = deleted_at()

    __table_args__ = (
        CheckConstraint(f"type IN ({_ACCOUNT_TYPES})", name="ck_accounts_type"),
        CheckConstraint(
            "tracking_mode IN ('transactions', 'balance_only')",
            name="ck_accounts_tracking_mode",
        ),
        Index("ix_accounts_household", "household_id"),
        Index("ix_accounts_household_type", "household_id", "type"),
    )


class Category(Base):
    """Spending/income taxonomy. household_id NULL = system default category."""

    __tablename__ = "categories"

    id: Mapped[int] = id_pk()
    household_id: Mapped[int | None] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), nullable=True
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    is_system: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = created_at()
    deleted_at: Mapped[datetime | None] = deleted_at()

    __table_args__ = (
        CheckConstraint(
            "type IN ('income', 'expense', 'transfer')", name="ck_categories_type"
        ),
        UniqueConstraint(
            "household_id", "parent_id", "name", name="uq_categories_scope_name"
        ),
        Index("ix_categories_household", "household_id"),
    )


class Transaction(Base):
    """Canonical, provider-independent transaction (R0 columns).

    Deferred to later migrations: merchant_id, transfer_id, refund_of,
    recurring_series_id, import_batch_id, imported_record_id, connection_id.
    """

    __tablename__ = "transactions"

    id: Mapped[int] = id_pk()
    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    public_id: Mapped[str] = public_uuid()

    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    booked_date: Mapped[date] = mapped_column(Date, nullable=False)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="posted")

    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    raw_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    source: Mapped[str] = mapped_column(String(12), nullable=False)
    dedup_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime | None] = updated_at()
    deleted_at: Mapped[datetime | None] = deleted_at()

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'posted')", name="ck_transactions_status"
        ),
        CheckConstraint(
            "source IN ('csv', 'ofx', 'pdf', 'aggregator', 'manual')",
            name="ck_transactions_source",
        ),
        # Strong dedup on a provider-supplied stable id, when present.
        Index(
            "uq_transactions_external_id",
            "household_id",
            "account_id",
            "external_id",
            unique=True,
            postgresql_where=text("external_id IS NOT NULL"),
        ),
        Index(
            "ix_transactions_account_date",
            "household_id",
            "account_id",
            "booked_date",
        ),
        Index(
            "ix_transactions_category_date",
            "household_id",
            "category_id",
            "booked_date",
        ),
        Index("ix_transactions_fingerprint", "dedup_fingerprint"),
    )
