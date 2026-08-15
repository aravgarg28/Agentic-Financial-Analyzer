"""Ingestion service — upload + batch lifecycle (T-070).

Handles the entry point of the CSV pipeline: validate an uploaded file, store it
as a Document (bytea), and open a staged ImportBatch. Idempotent by file
checksum — re-uploading the same file returns the existing batch instead of
duplicating. Parsing/mapping/dedup/commit are later tasks (T-071+).
"""
from __future__ import annotations

import hashlib

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.modules.ingestion import coerce, parser, presets
from app.modules.ingestion.mapping import MappingSpec, suggest_mapping
from app.modules.ingestion.models import (
    ColumnMapping,
    Document,
    ImportBatch,
    ImportedRecord,
)
from app.modules.ledger.accounts import resolve_institution
from app.modules.ledger.service import LedgerError, resolve_account

PREVIEW_SAMPLE_ROWS = 10

# Only CSV/plain text in R1. Extensions and (loose) content types are checked;
# the file is parsed as CSV, never executed.
ALLOWED_EXTENSIONS = (".csv", ".txt")
ALLOWED_CONTENT_TYPES = {
    "text/csv",
    "text/plain",
    "application/csv",
    "application/vnd.ms-excel",  # some browsers label .csv this way
    "application/octet-stream",  # generic; extension gate still applies
    "",
    None,
}
_ACTIVE_BATCH_STATUSES = ("staged", "committing", "committed")


class UploadError(LedgerError):
    """Invalid upload (bad type/size, quota exceeded)."""


def compute_checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_file(filename: str, content_type: str | None, data: bytes) -> None:
    lower = (filename or "").lower()
    if not lower.endswith(ALLOWED_EXTENSIONS):
        raise UploadError("Only .csv or .txt files are accepted.")
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise UploadError(f"Unsupported content type: {content_type!r}.")
    if len(data) == 0:
        raise UploadError("The file is empty.")
    if len(data) > settings.max_upload_bytes:
        mb = settings.max_upload_bytes // (1024 * 1024)
        raise UploadError(f"File exceeds the {mb} MB limit.")


async def _check_quota(session: AsyncSession, household_id: int, incoming: int) -> None:
    used = await session.scalar(
        select(func.coalesce(func.sum(Document.byte_size), 0)).where(
            Document.household_id == household_id, Document.deleted_at.is_(None)
        )
    )
    if int(used or 0) + incoming > settings.household_document_quota_bytes:
        raise UploadError("Document storage quota exceeded for this household.")


async def upload_csv(
    session: AsyncSession,
    *,
    household_id: int,
    filename: str,
    content_type: str | None,
    data: bytes,
    account_public_id: str | None = None,
) -> tuple[ImportBatch, bool]:
    """Validate + store a CSV and open a staged batch. Returns (batch, created).

    created=False means an identical file (same checksum) is already imported or
    staged — the existing batch is returned rather than duplicating (FIN-05)."""
    _validate_file(filename, content_type, data)

    account_id: int | None = None
    if account_public_id:
        account = await resolve_account(session, household_id, account_public_id)
        account_id = account.id

    checksum = compute_checksum(data)

    existing = await session.scalar(
        select(ImportBatch).where(
            ImportBatch.household_id == household_id,
            ImportBatch.file_checksum == checksum,
            ImportBatch.status.in_(_ACTIVE_BATCH_STATUSES),
        )
    )
    if existing is not None:
        return existing, False

    await _check_quota(session, household_id, len(data))

    document = Document(
        household_id=household_id,
        kind="csv",
        filename=filename[:255],
        content_type=(content_type or None),
        byte_size=len(data),
        checksum=checksum,
        content=data,
    )
    session.add(document)
    await session.flush()

    batch = ImportBatch(
        household_id=household_id,
        account_id=account_id,
        source="csv",
        filename=filename[:255],
        file_document_id=document.id,
        file_checksum=checksum,
        status="staged",
    )
    session.add(batch)
    await session.flush()
    return batch, True


def serialize_batch(batch: ImportBatch) -> dict:
    return {
        "id": batch.public_id,
        "status": batch.status,
        "filename": batch.filename,
        "source": batch.source,
        "row_count": batch.row_count,
        "new_count": batch.new_count,
        "dup_count": batch.dup_count,
    }


# --------------------------------------------------------------------------- #
# Batch/document resolution + preview + mappings (T-071)
# --------------------------------------------------------------------------- #
async def resolve_batch(
    session: AsyncSession, household_id: int, public_id: str
) -> ImportBatch:
    batch = await session.scalar(
        select(ImportBatch).where(
            ImportBatch.public_id == public_id,
            ImportBatch.household_id == household_id,
        )
    )
    if batch is None:
        raise UploadError("Import batch not found.")
    return batch


async def _load_document(session: AsyncSession, household_id: int, document_id: int) -> Document:
    doc = await session.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.household_id == household_id,
            Document.deleted_at.is_(None),
        )
    )
    if doc is None:
        raise UploadError("Uploaded file not found.")
    return doc


async def preview_batch(
    session: AsyncSession, household_id: int, batch_public_id: str
) -> dict:
    """Sniff the uploaded CSV and return headers + sample rows, an auto-suggested
    mapping, matching built-in presets, and the household's saved mappings."""
    batch = await resolve_batch(session, household_id, batch_public_id)
    if batch.file_document_id is None:
        raise UploadError("This batch has no associated file.")
    doc = await _load_document(session, household_id, batch.file_document_id)

    parsed = parser.parse_csv(doc.content, sample_limit=PREVIEW_SAMPLE_ROWS)
    suggested, notes = suggest_mapping(parsed.headers)
    saved = await list_mappings(session, household_id)

    return {
        "batch_id": batch.public_id,
        "encoding": parsed.encoding,
        "delimiter": parsed.delimiter,
        "headers": parsed.headers,
        "sample_rows": parsed.rows,
        "total_rows": parsed.total_rows,
        "suggested_mapping": suggested.model_dump() if suggested else None,
        "suggestion_notes": notes,
        "presets": [presets.serialize_preset(p) for p in presets.match_presets(parsed.headers)],
        "saved_mappings": [serialize_mapping(m) for m in saved],
    }


async def list_mappings(session: AsyncSession, household_id: int) -> list[ColumnMapping]:
    result = await session.execute(
        select(ColumnMapping)
        .where(
            ColumnMapping.household_id == household_id,
            ColumnMapping.deleted_at.is_(None),
        )
        .order_by(ColumnMapping.name)
    )
    return list(result.scalars().all())


async def save_mapping(
    session: AsyncSession,
    *,
    household_id: int,
    name: str,
    mapping: MappingSpec,
    institution_public_id: str | None = None,
) -> ColumnMapping:
    clean = name.strip()
    if not clean:
        raise UploadError("Mapping name is required.")
    institution_id: int | None = None
    if institution_public_id:
        inst = await resolve_institution(session, household_id, institution_public_id)
        institution_id = inst.id
    row = ColumnMapping(
        household_id=household_id,
        institution_id=institution_id,
        name=clean,
        mapping=mapping.model_dump(),
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as exc:  # unique (household_id, name)
        await session.rollback()
        raise UploadError("A mapping with that name already exists.") from exc
    return row


def serialize_mapping(row: ColumnMapping) -> dict:
    return {
        "id": row.public_id,
        "name": row.name,
        "mapping": row.mapping,
    }


# --------------------------------------------------------------------------- #
# Staging: apply a mapping -> imported_records with parsed values + validation
# (T-072)
# --------------------------------------------------------------------------- #
def _coerce_row(row: dict[str, str], mapping: MappingSpec) -> dict:
    """Parse one raw row into canonical fields + a validation record. Money goes
    straight to integer minor units via Decimal (never float)."""
    errors: list[str] = []
    warnings: list[str] = []

    amount_minor: int | None = None
    if mapping.amount.mode == "single":
        minor, err = coerce.parse_amount_minor(row.get(mapping.amount.column or "", ""))
        if err:
            errors.append(f"amount: {err}")
        else:
            amount_minor = coerce.apply_sign_convention(minor, mapping.amount.sign)
    else:
        minor, err = coerce.parse_amount_debit_credit(
            row.get(mapping.amount.debit_column or ""),
            row.get(mapping.amount.credit_column or ""),
        )
        if err:
            errors.append(f"amount: {err}")
        else:
            amount_minor = minor

    parsed_date, derr = coerce.parse_date(
        row.get(mapping.date.column, ""), mapping.date.format
    )
    if derr:
        errors.append(f"date: {derr}")

    description = (row.get(mapping.description_column, "") or "").strip()
    if not description:
        warnings.append("empty description")

    return {
        "amount_minor": amount_minor,
        "date": parsed_date,
        "currency": mapping.currency,
        "description": description or None,
        "validation": {"errors": errors, "warnings": warnings},
    }


async def stage_batch(
    session: AsyncSession,
    *,
    household_id: int,
    batch_public_id: str,
    mapping: MappingSpec,
) -> dict:
    """Apply ``mapping`` to the batch's CSV, (re)creating imported_records with
    parsed values + per-row validation. Re-runnable: existing staged records are
    cleared first so the user can fix the mapping and re-stage. Dedup verdicts
    are assigned separately (T-073)."""
    batch = await resolve_batch(session, household_id, batch_public_id)
    if batch.status != "staged":
        raise UploadError("This batch can no longer be staged.")
    if batch.file_document_id is None:
        raise UploadError("This batch has no associated file.")
    doc = await _load_document(session, household_id, batch.file_document_id)

    parsed = parser.parse_csv(doc.content, skip_rows=mapping.skip_rows)
    missing = mapping.validate_against(parsed.headers)
    if missing:
        raise UploadError(f"Mapping references columns not in the file: {missing}")

    # Clear any previous staging for this batch (idempotent re-stage).
    await session.execute(
        delete(ImportedRecord).where(ImportedRecord.import_batch_id == batch.id)
    )

    error_count = 0
    for row_number, row in enumerate(parsed.rows, start=1):
        coerced = _coerce_row(row, mapping)
        if coerced["validation"]["errors"]:
            error_count += 1
        session.add(
            ImportedRecord(
                household_id=household_id,
                import_batch_id=batch.id,
                row_number=row_number,
                raw=row,
                parsed_amount_minor=coerced["amount_minor"],
                parsed_date=coerced["date"],
                parsed_currency=coerced["currency"],
                parsed_description=coerced["description"],
                validation=coerced["validation"],
                user_decision="pending",
            )
        )

    batch.row_count = len(parsed.rows)
    await session.flush()
    return {
        "batch_id": batch.public_id,
        "total": len(parsed.rows),
        "errors": error_count,
        "valid": len(parsed.rows) - error_count,
    }
