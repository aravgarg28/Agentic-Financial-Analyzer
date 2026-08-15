"""Ingestion module models (T-070): the CSV import pipeline tables.

The canonical flow is stage -> validate -> dedup -> review -> commit
(ingestion-design.md). Every source funnels through these tables so dedup and
correctness live in one place. Money in imported_records is parsed straight to
integer minor units (never float) at staging time.
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
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.modules._columns import created_at, deleted_at, id_pk, public_uuid


class Document(Base):
    """An uploaded artifact (CSV now; OFX/PDF later). Small files are stored as
    bytea directly (ADR-08, free-tier). Never executed or served inline."""

    __tablename__ = "documents"

    id: Mapped[int] = id_pk()
    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), nullable=False
    )
    public_id: Mapped[str] = public_uuid()
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = created_at()
    deleted_at: Mapped[datetime | None] = deleted_at()

    __table_args__ = (
        CheckConstraint("kind IN ('csv', 'ofx', 'pdf')", name="ck_documents_kind"),
        Index("ix_documents_household", "household_id"),
    )


class ColumnMapping(Base):
    """A saved per-institution CSV column mapping (source col -> canonical field,
    sign convention, date format), reusable across imports."""

    __tablename__ = "column_mappings"

    id: Mapped[int] = id_pk()
    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), nullable=False
    )
    institution_id: Mapped[int | None] = mapped_column(
        ForeignKey("institutions.id", ondelete="SET NULL"), nullable=True
    )
    public_id: Mapped[str] = public_uuid()
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    mapping: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = created_at()
    deleted_at: Mapped[datetime | None] = deleted_at()

    __table_args__ = (
        UniqueConstraint("household_id", "name", name="uq_column_mappings_scope_name"),
        Index("ix_column_mappings_household", "household_id"),
    )


class ImportBatch(Base):
    """One import run. Identified for idempotency by file_checksum; re-uploading
    the same file surfaces 'already imported' instead of duplicating."""

    __tablename__ = "import_batches"

    id: Mapped[int] = id_pk()
    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    public_id: Mapped[str] = public_uuid()
    source: Mapped[str] = mapped_column(String(12), nullable=False, server_default="csv")
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    file_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    column_mapping_id: Mapped[int | None] = mapped_column(
        ForeignKey("column_mappings.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(12), nullable=False, server_default="staged")
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    new_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    dup_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = created_at()
    committed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('staged', 'committing', 'committed', 'rolled_back', 'failed')",
            name="ck_import_batches_status",
        ),
        Index("ix_import_batches_household", "household_id"),
        Index("ix_import_batches_status", "household_id", "status"),
        # Idempotency: the same file cannot be staged twice while live.
        Index(
            "uq_import_batches_active_checksum",
            "household_id",
            "file_checksum",
            unique=True,
            postgresql_where="status IN ('staged', 'committing', 'committed')",
        ),
    )


class ImportedRecord(Base):
    """A staged raw row pre-commit, carrying parsed fields, validation results,
    a dedup verdict, and the user's decision. Becomes a Transaction on commit."""

    __tablename__ = "imported_records"

    id: Mapped[int] = id_pk()
    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), nullable=False
    )
    import_batch_id: Mapped[int] = mapped_column(
        ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
    parsed_amount_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    parsed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    parsed_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    parsed_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    dedup_verdict: Mapped[str | None] = mapped_column(String(10), nullable=True)
    user_decision: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default="pending"
    )
    committed_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = created_at()

    __table_args__ = (
        CheckConstraint(
            "dedup_verdict IS NULL OR dedup_verdict IN ('new', 'duplicate', 'near_dup')",
            name="ck_imported_records_verdict",
        ),
        CheckConstraint(
            "user_decision IN ('pending', 'accept', 'skip', 'merge')",
            name="ck_imported_records_decision",
        ),
        Index("ix_imported_records_batch_row", "import_batch_id", "row_number"),
    )
