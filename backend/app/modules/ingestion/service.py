"""Ingestion service — upload + batch lifecycle (T-070).

Handles the entry point of the CSV pipeline: validate an uploaded file, store it
as a Document (bytea), and open a staged ImportBatch. Idempotent by file
checksum — re-uploading the same file returns the existing batch instead of
duplicating. Parsing/mapping/dedup/commit are later tasks (T-071+).
"""
from __future__ import annotations

import hashlib

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.modules.ingestion.models import Document, ImportBatch
from app.modules.ledger.service import LedgerError, resolve_account

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
