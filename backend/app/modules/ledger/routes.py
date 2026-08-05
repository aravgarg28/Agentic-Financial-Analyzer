"""Ledger HTTP routes (T-021 slice): list accounts, add manual transaction.

Account-scoped and tenant-isolated via the session Principal. Money crosses the
API boundary as integer minor units, matching storage (no float — FIN-01)."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from fastapi import status as http_status
from fastapi.exceptions import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.modules.identity.audit import record_audit
from app.modules.identity.deps import csrf_guard, require_principal
from app.modules.identity.service import Principal
from app.modules.ledger import service
from app.modules.ledger.models import Account

router = APIRouter(prefix="/ledger", tags=["Ledger"])


@router.get("/accounts")
async def list_accounts(
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_principal),
) -> dict:
    stmt = (
        select(Account)
        .where(
            Account.household_id == principal.household_id,
            Account.deleted_at.is_(None),
            Account.archived_at.is_(None),
        )
        .order_by(Account.name)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return {
        "data": [
            {
                "id": a.public_id,
                "name": a.name,
                "type": a.type,
                "currency": a.currency,
                "current_balance_minor": a.current_balance_minor,
            }
            for a in rows
        ]
    }


class TransactionInput(BaseModel):
    account_id: str = Field(..., description="Account public id")
    amount_minor: int = Field(..., description="Signed minor units; <0 = expense")
    booked_date: date
    description: str | None = Field(None, max_length=500)
    category_id: int | None = None


@router.post("/transactions", status_code=http_status.HTTP_201_CREATED)
async def add_transaction(
    data: TransactionInput,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_principal),
    _csrf: None = Depends(csrf_guard),
) -> dict:
    try:
        tx, created = await service.add_manual_transaction(
            db,
            household_id=principal.household_id,
            account_public_id=data.account_id,
            amount_minor=data.amount_minor,
            booked_date=data.booked_date,
            raw_description=data.description,
            category_id=data.category_id,
        )
    except service.LedgerError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    if created:
        await record_audit(
            db,
            action="transaction.create_manual",
            household_id=principal.household_id,
            actor_user_id=principal.user_id,
            target_type="transaction",
            target_public_id=tx.public_id,
        )
    await db.commit()
    return {
        "status": "ok",
        "created": created,
        "id": tx.public_id,
        "amount_minor": tx.amount_minor,
        "currency": tx.currency,
    }
