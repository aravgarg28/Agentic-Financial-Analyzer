"""Ingestion HTTP routes (T-070): CSV upload -> staged import batch.

The first file-handling surface, so validation is strict: extension + content
type allowlist, size cap, per-household quota, and idempotency by checksum. The
file is stored and parsed as data, never executed or served inline.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi import status as http_status
from fastapi.exceptions import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.modules.identity.audit import record_audit
from app.modules.identity.deps import csrf_guard, require_principal
from app.modules.identity.service import Principal
from app.modules.ingestion import service
from app.modules.ingestion.mapping import MappingSpec

router = APIRouter(prefix="/imports", tags=["Imports"])


def _bad_request(exc: service.LedgerError) -> HTTPException:
    return HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _parse_int_id(raw: str) -> int:
    """Parse a path id to int. Kept a str path param so anonymous requests hit
    auth (401) instead of FastAPI int-coercion (422)."""
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="Not found."
        ) from exc


@router.post("/upload", status_code=http_status.HTTP_201_CREATED)
async def upload_csv(
    file: UploadFile = File(...),
    account_id: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_principal),
    _csrf: None = Depends(csrf_guard),
) -> dict:
    data = await file.read()
    # Guard against oversized reads even before service validation.
    if len(data) > settings.max_upload_bytes:
        mb = settings.max_upload_bytes // (1024 * 1024)
        raise HTTPException(
            status_code=http_status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {mb} MB limit.",
        )
    try:
        batch, created = await service.upload_csv(
            db,
            household_id=principal.household_id,
            filename=file.filename or "upload.csv",
            content_type=file.content_type,
            data=data,
            account_public_id=account_id,
        )
    except service.LedgerError as exc:
        # UploadError (bad type/size/quota) and a bad account both surface as 400.
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    if created:
        await record_audit(
            db,
            action="import.upload",
            household_id=principal.household_id,
            actor_user_id=principal.user_id,
            target_type="import_batch",
            target_public_id=batch.public_id,
            metadata={"filename": batch.filename, "bytes": len(data)},
        )
    await db.commit()
    return {**service.serialize_batch(batch), "created": created}


@router.get("/{batch_id}/preview")
async def preview_batch(
    batch_id: str,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_principal),
) -> dict:
    try:
        return await service.preview_batch(db, principal.household_id, batch_id)
    except service.LedgerError as exc:
        raise _bad_request(exc) from exc


class MappingCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    mapping: MappingSpec
    institution_id: str | None = None


class StageRequest(BaseModel):
    mapping: MappingSpec


@router.post("/{batch_id}/stage")
async def stage_batch(
    batch_id: str,
    data: StageRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_principal),
    _csrf: None = Depends(csrf_guard),
) -> dict:
    try:
        summary = await service.stage_batch(
            db,
            household_id=principal.household_id,
            batch_public_id=batch_id,
            mapping=data.mapping,
        )
    except service.LedgerError as exc:
        raise _bad_request(exc) from exc
    await record_audit(
        db,
        action="import.stage",
        household_id=principal.household_id,
        actor_user_id=principal.user_id,
        target_type="import_batch",
        target_public_id=batch_id,
        metadata={"rows": summary["total"], "errors": summary["errors"]},
    )
    await db.commit()
    return summary


@router.get("/{batch_id}/records")
async def list_records(
    batch_id: str,
    verdict: str | None = Query(None),
    decision: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_principal),
) -> dict:
    try:
        batch, rows, total = await service.list_records(
            db, principal.household_id, batch_id,
            offset=offset, limit=limit, verdict=verdict, decision=decision,
        )
    except service.LedgerError as exc:
        raise _bad_request(exc) from exc
    return {
        "batch": service.serialize_batch(batch),
        "total": total,
        "data": [service.serialize_record(r) for r in rows],
    }


class RecordDecision(BaseModel):
    decision: str | None = None
    category_id: int | None = None


@router.patch("/{batch_id}/records/{row_number}")
async def update_record(
    batch_id: str,
    row_number: str,
    data: RecordDecision,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_principal),
    _csrf: None = Depends(csrf_guard),
) -> dict:
    provided = data.model_dump(exclude_unset=True)
    try:
        record = await service.set_record_decision(
            db,
            household_id=principal.household_id,
            batch_public_id=batch_id,
            row_number=_parse_int_id(row_number),
            decision=data.decision,
            category_id=data.category_id,
            set_category="category_id" in provided,
        )
    except service.LedgerError as exc:
        raise _bad_request(exc) from exc
    await db.commit()
    return service.serialize_record(record)


class BulkDecision(BaseModel):
    decision: str
    verdict: str | None = None


@router.post("/{batch_id}/records/bulk")
async def bulk_update_records(
    batch_id: str,
    data: BulkDecision,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_principal),
    _csrf: None = Depends(csrf_guard),
) -> dict:
    try:
        summary = await service.bulk_set_decision(
            db,
            household_id=principal.household_id,
            batch_public_id=batch_id,
            decision=data.decision,
            verdict=data.verdict,
        )
    except service.LedgerError as exc:
        raise _bad_request(exc) from exc
    await db.commit()
    return summary


@router.post("/{batch_id}/commit")
async def commit_batch(
    batch_id: str,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_principal),
    _csrf: None = Depends(csrf_guard),
) -> dict:
    try:
        summary = await service.commit_batch(
            db, household_id=principal.household_id, batch_public_id=batch_id
        )
    except service.LedgerError as exc:
        raise _bad_request(exc) from exc
    await record_audit(
        db,
        action="import.commit",
        household_id=principal.household_id,
        actor_user_id=principal.user_id,
        target_type="import_batch",
        target_public_id=batch_id,
        metadata={"committed": summary["committed"]},
    )
    await db.commit()
    return summary


@router.post("/{batch_id}/rollback")
async def rollback_batch(
    batch_id: str,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_principal),
    _csrf: None = Depends(csrf_guard),
) -> dict:
    try:
        summary = await service.rollback_batch(
            db, household_id=principal.household_id, batch_public_id=batch_id
        )
    except service.LedgerError as exc:
        raise _bad_request(exc) from exc
    await record_audit(
        db,
        action="import.rollback",
        household_id=principal.household_id,
        actor_user_id=principal.user_id,
        target_type="import_batch",
        target_public_id=batch_id,
        metadata={"deleted": summary["deleted"]},
    )
    await db.commit()
    return summary


class DedupRequest(BaseModel):
    account_id: str | None = None


@router.post("/{batch_id}/dedup")
async def dedup_batch(
    batch_id: str,
    data: DedupRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_principal),
    _csrf: None = Depends(csrf_guard),
) -> dict:
    try:
        summary = await service.dedup_batch(
            db,
            household_id=principal.household_id,
            batch_public_id=batch_id,
            account_public_id=data.account_id,
        )
    except service.LedgerError as exc:
        raise _bad_request(exc) from exc
    await db.commit()
    return summary


@router.get("/mappings")
async def list_mappings(
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_principal),
) -> dict:
    rows = await service.list_mappings(db, principal.household_id)
    return {"data": [service.serialize_mapping(m) for m in rows]}


@router.post("/mappings", status_code=http_status.HTTP_201_CREATED)
async def create_mapping(
    data: MappingCreate,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_principal),
    _csrf: None = Depends(csrf_guard),
) -> dict:
    try:
        row = await service.save_mapping(
            db,
            household_id=principal.household_id,
            name=data.name,
            mapping=data.mapping,
            institution_public_id=data.institution_id,
        )
    except service.LedgerError as exc:
        raise _bad_request(exc) from exc
    await db.commit()
    return service.serialize_mapping(row)
