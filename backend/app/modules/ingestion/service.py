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
from app.modules.ledger import accounts as ledger_accounts
from app.modules.ledger.accounts import resolve_institution
from app.modules.ledger.models import Account, Transaction
from app.modules.ledger.service import (
    LedgerError,
    compute_fingerprint,
    normalize_description,
    resolve_account,
    resolve_category_id,
    resolve_or_create_merchant,
)

PREVIEW_SAMPLE_ROWS = 10
COMMIT_CHUNK = 500
VALID_DECISIONS = frozenset({"accept", "skip", "merge"})

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


# --------------------------------------------------------------------------- #
# Duplicate detection (T-073)
# --------------------------------------------------------------------------- #
def record_fingerprint(account_id: int, record: ImportedRecord) -> str | None:
    """Deterministic dedup key for a staged record, or None if it lacks the
    parsed fields (a row with validation errors). Same basis as manual
    transactions, so re-importing a manually-entered row also dedups."""
    if record.parsed_amount_minor is None or record.parsed_date is None:
        return None
    return compute_fingerprint(
        account_id=account_id,
        booked_date=record.parsed_date,
        amount_minor=record.parsed_amount_minor,
        normalized_desc=normalize_description(record.parsed_description),
    )


async def dedup_batch(
    session: AsyncSession,
    *,
    household_id: int,
    batch_public_id: str,
    account_public_id: str | None = None,
) -> dict:
    """Assign a dedup verdict to every staged record, comparing against the
    committed ledger (exact fingerprint -> 'duplicate') and within the batch
    (repeat fingerprint -> 'near_dup', kept for user review, never auto-dropped).
    Requires the batch's target account. Sets default per-row decisions:
    new -> accept, duplicate -> skip, near_dup -> pending."""
    batch = await resolve_batch(session, household_id, batch_public_id)
    if batch.status != "staged":
        raise UploadError("This batch can no longer be deduplicated.")

    # Resolve the target account (from the batch, or set it now).
    if account_public_id:
        account = await resolve_account(session, household_id, account_public_id)
        batch.account_id = account.id
    if batch.account_id is None:
        raise UploadError("Select an account for this import before de-duplicating.")
    account_id = batch.account_id

    committed = set(
        (
            await session.execute(
                select(Transaction.dedup_fingerprint).where(
                    Transaction.household_id == household_id,
                    Transaction.account_id == account_id,
                    Transaction.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )

    records = list(
        (
            await session.execute(
                select(ImportedRecord)
                .where(ImportedRecord.import_batch_id == batch.id)
                .order_by(ImportedRecord.row_number)
            )
        )
        .scalars()
        .all()
    )

    seen_in_batch: set[str] = set()
    counts = {"new": 0, "duplicate": 0, "near_dup": 0, "error": 0}
    for record in records:
        if record.validation and record.validation.get("errors"):
            record.dedup_verdict = None
            record.user_decision = "skip"
            counts["error"] += 1
            continue
        fp = record_fingerprint(account_id, record)
        if fp is None:
            record.dedup_verdict = None
            record.user_decision = "skip"
            counts["error"] += 1
            continue
        if fp in committed:
            record.dedup_verdict = "duplicate"
            record.user_decision = "skip"
            counts["duplicate"] += 1
        elif fp in seen_in_batch:
            record.dedup_verdict = "near_dup"
            record.user_decision = "pending"
            counts["near_dup"] += 1
        else:
            record.dedup_verdict = "new"
            record.user_decision = "accept"
            counts["new"] += 1
            seen_in_batch.add(fp)

    batch.new_count = counts["new"]
    batch.dup_count = counts["duplicate"]
    await session.flush()
    return {"batch_id": batch.public_id, **counts}


# --------------------------------------------------------------------------- #
# Review (list/decide) + commit (T-074)
# --------------------------------------------------------------------------- #
def _has_errors(record: ImportedRecord) -> bool:
    return bool(record.validation and record.validation.get("errors"))


def serialize_record(record: ImportedRecord) -> dict:
    return {
        "row_number": record.row_number,
        "raw": record.raw,
        "amount_minor": record.parsed_amount_minor,
        "date": record.parsed_date.isoformat() if record.parsed_date else None,
        "currency": record.parsed_currency,
        "description": record.parsed_description,
        "category_id": record.category_id,
        "verdict": record.dedup_verdict,
        "decision": record.user_decision,
        "validation": record.validation,
        "committed": record.committed_transaction_id is not None,
    }


async def list_records(
    session: AsyncSession,
    household_id: int,
    batch_public_id: str,
    *,
    offset: int = 0,
    limit: int = 100,
    verdict: str | None = None,
    decision: str | None = None,
) -> tuple[ImportBatch, list[ImportedRecord], int]:
    batch = await resolve_batch(session, household_id, batch_public_id)
    conds = [ImportedRecord.import_batch_id == batch.id]
    if verdict:
        conds.append(ImportedRecord.dedup_verdict == verdict)
    if decision:
        conds.append(ImportedRecord.user_decision == decision)
    total = await session.scalar(
        select(func.count()).select_from(ImportedRecord).where(*conds)
    )
    rows = list(
        (
            await session.execute(
                select(ImportedRecord)
                .where(*conds)
                .order_by(ImportedRecord.row_number)
                .offset(offset)
                .limit(min(limit, 500))
            )
        )
        .scalars()
        .all()
    )
    return batch, rows, int(total or 0)


async def _resolve_record(
    session: AsyncSession, batch: ImportBatch, row_number: int
) -> ImportedRecord:
    record = await session.scalar(
        select(ImportedRecord).where(
            ImportedRecord.import_batch_id == batch.id,
            ImportedRecord.row_number == row_number,
        )
    )
    if record is None:
        raise UploadError("Record not found.")
    return record


async def set_record_decision(
    session: AsyncSession,
    *,
    household_id: int,
    batch_public_id: str,
    row_number: int,
    decision: str | None = None,
    category_id: int | None = None,
    set_category: bool = False,
) -> ImportedRecord:
    batch = await resolve_batch(session, household_id, batch_public_id)
    if batch.status != "staged":
        raise UploadError("This batch can no longer be edited.")
    record = await _resolve_record(session, batch, row_number)
    if decision is not None:
        if decision not in VALID_DECISIONS:
            raise UploadError(f"Invalid decision: {decision!r}.")
        if decision == "accept" and _has_errors(record):
            raise UploadError("A row with validation errors cannot be accepted.")
        record.user_decision = decision
    if set_category:
        record.category_id = await resolve_category_id(session, household_id, category_id)
    await session.flush()
    return record


async def bulk_set_decision(
    session: AsyncSession,
    *,
    household_id: int,
    batch_public_id: str,
    decision: str,
    verdict: str | None = None,
) -> dict:
    """Apply a decision to every record (optionally filtered by verdict). Rows
    with validation errors are never auto-accepted."""
    if decision not in VALID_DECISIONS:
        raise UploadError(f"Invalid decision: {decision!r}.")
    batch = await resolve_batch(session, household_id, batch_public_id)
    if batch.status != "staged":
        raise UploadError("This batch can no longer be edited.")
    conds = [ImportedRecord.import_batch_id == batch.id]
    if verdict:
        conds.append(ImportedRecord.dedup_verdict == verdict)
    records = list((await session.execute(select(ImportedRecord).where(*conds))).scalars().all())
    changed = 0
    for record in records:
        if decision == "accept" and _has_errors(record):
            continue
        record.user_decision = decision
        changed += 1
    await session.flush()
    return {"batch_id": batch.public_id, "updated": changed}


async def commit_batch(
    session: AsyncSession, *, household_id: int, batch_public_id: str
) -> dict:
    """Insert one Transaction per accepted, error-free record, in a single
    transaction (the caller commits). Atomic: any failure leaves the batch
    'staged' with no rows written. Chunked flushes keep memory bounded so a
    10k-row batch commits within the request window."""
    batch = await resolve_batch(session, household_id, batch_public_id)
    if batch.status != "staged":
        raise UploadError("Only a staged batch can be committed.")
    if batch.account_id is None:
        raise UploadError("Select an account and run de-duplication before committing.")
    account = await session.get(Account, batch.account_id)
    if account is None or account.household_id != household_id:
        raise UploadError("Import account not found.")

    batch.status = "committing"
    await session.flush()

    records = list(
        (
            await session.execute(
                select(ImportedRecord)
                .where(ImportedRecord.import_batch_id == batch.id)
                .order_by(ImportedRecord.row_number)
            )
        )
        .scalars()
        .all()
    )

    committed = 0
    total_minor = 0
    pending: list[tuple[ImportedRecord, Transaction]] = []

    async def _flush_pending() -> None:
        await session.flush()
        for rec, tx in pending:
            rec.committed_transaction_id = tx.id
        pending.clear()

    for record in records:
        if record.user_decision != "accept" or _has_errors(record):
            continue
        if record.parsed_amount_minor is None or record.parsed_date is None:
            continue
        normalized = normalize_description(record.parsed_description)
        merchant = await resolve_or_create_merchant(session, household_id, normalized)
        currency = record.parsed_currency or account.currency
        fingerprint = compute_fingerprint(
            account_id=account.id,
            booked_date=record.parsed_date,
            amount_minor=record.parsed_amount_minor,
            normalized_desc=normalized,
        )
        tx = Transaction(
            household_id=household_id,
            account_id=account.id,
            merchant_id=merchant.id if merchant else None,
            import_batch_id=batch.id,
            imported_record_id=record.id,
            amount_minor=record.parsed_amount_minor,
            currency=currency,
            booked_date=record.parsed_date,
            status="posted",
            category_id=record.category_id,
            raw_description=record.parsed_description,
            normalized_description=normalized or None,
            source="csv",
            dedup_fingerprint=fingerprint,
        )
        session.add(tx)
        pending.append((record, tx))
        committed += 1
        total_minor += record.parsed_amount_minor
        if len(pending) >= COMMIT_CHUNK:
            await _flush_pending()

    if pending:
        await _flush_pending()

    # Refresh the cached balance (patchable point; failure here rolls everything
    # back, leaving the batch 'staged').
    await ledger_accounts.recompute_account_balance(session, account)

    from datetime import UTC, datetime

    batch.status = "committed"
    batch.committed_at = datetime.now(UTC)
    await session.flush()
    return {
        "batch_id": batch.public_id,
        "committed": committed,
        "total_minor": total_minor,
    }
