"""Ingestion HTTP routes (T-070): CSV upload -> staged import batch.

The first file-handling surface, so validation is strict: extension + content
type allowlist, size cap, per-household quota, and idempotency by checksum. The
file is stored and parsed as data, never executed or served inline.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi import status as http_status
from fastapi.exceptions import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.modules.identity.audit import record_audit
from app.modules.identity.deps import csrf_guard, require_principal
from app.modules.identity.service import Principal
from app.modules.ingestion import service

router = APIRouter(prefix="/imports", tags=["Imports"])


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
