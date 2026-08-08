"""Ledger HTTP routes: accounts + institutions CRUD (T-060) and manual
transaction add (T-021).

Everything is account-scoped and tenant-isolated via the session Principal.
Money crosses the API boundary as integer minor units (no float — FIN-01)."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi import status as http_status
from fastapi.exceptions import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.modules.identity.audit import record_audit
from app.modules.identity.deps import csrf_guard, require_principal
from app.modules.identity.service import Principal
from app.modules.ledger import accounts as accounts_service
from app.modules.ledger import service

router = APIRouter(prefix="/ledger", tags=["Ledger"])


def _bad_request(exc: service.LedgerError) -> HTTPException:
    return HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(exc))


# --------------------------------------------------------------------------- #
# Institutions
# --------------------------------------------------------------------------- #
class InstitutionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    kind: str | None = Field(None, max_length=40)


@router.get("/institutions")
async def list_institutions(
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_principal),
) -> dict:
    rows = await accounts_service.list_institutions(db, principal.household_id)
    return {"data": [accounts_service.serialize_institution(i) for i in rows]}


@router.post("/institutions", status_code=http_status.HTTP_201_CREATED)
async def create_institution(
    data: InstitutionCreate,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_principal),
    _csrf: None = Depends(csrf_guard),
) -> dict:
    try:
        inst = await accounts_service.create_institution(
            db, household_id=principal.household_id, name=data.name, kind=data.kind
        )
    except service.LedgerError as exc:
        raise _bad_request(exc) from exc
    await record_audit(
        db,
        action="institution.create",
        household_id=principal.household_id,
        actor_user_id=principal.user_id,
        target_type="institution",
        target_public_id=inst.public_id,
    )
    await db.commit()
    return accounts_service.serialize_institution(inst)


# --------------------------------------------------------------------------- #
# Accounts
# --------------------------------------------------------------------------- #
class AccountCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    type: str = Field(..., description="checking|savings|credit_card|loan|investment|property|cash|other")
    tracking_mode: str = Field("transactions", description="transactions|balance_only")
    currency: str | None = Field(None, min_length=3, max_length=3)
    institution_id: str | None = Field(None, description="Institution public id")
    opening_balance_minor: int | None = None


class AccountUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    institution_id: str | None = Field(None, description="Institution public id")
    clear_institution: bool = False
    current_balance_minor: int | None = None


async def _serialize_with_institutions(
    db: AsyncSession, household_id: int, accts: list
) -> list[dict]:
    """Serialize accounts, attaching their institution label (one lookup)."""
    insts = {
        i.id: i for i in await accounts_service.list_institutions(db, household_id)
    }
    return [
        accounts_service.serialize_account(a, institution=insts.get(a.institution_id))
        for a in accts
    ]


@router.get("/accounts")
async def list_accounts(
    include_archived: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_principal),
) -> dict:
    accts = await accounts_service.list_accounts(
        db, principal.household_id, include_archived=include_archived
    )
    return {"data": await _serialize_with_institutions(db, principal.household_id, accts)}


@router.post("/accounts", status_code=http_status.HTTP_201_CREATED)
async def create_account(
    data: AccountCreate,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_principal),
    _csrf: None = Depends(csrf_guard),
) -> dict:
    try:
        account = await accounts_service.create_account(
            db,
            household_id=principal.household_id,
            name=data.name,
            type=data.type,
            tracking_mode=data.tracking_mode,
            currency=data.currency,
            institution_public_id=data.institution_id,
            opening_balance_minor=data.opening_balance_minor,
        )
    except service.LedgerError as exc:
        raise _bad_request(exc) from exc
    await record_audit(
        db,
        action="account.create",
        household_id=principal.household_id,
        actor_user_id=principal.user_id,
        target_type="account",
        target_public_id=account.public_id,
        metadata={"type": account.type, "tracking_mode": account.tracking_mode},
    )
    await db.commit()
    (serialized,) = await _serialize_with_institutions(
        db, principal.household_id, [account]
    )
    return serialized


@router.patch("/accounts/{public_id}")
async def update_account(
    public_id: str,
    data: AccountUpdate,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_principal),
    _csrf: None = Depends(csrf_guard),
) -> dict:
    try:
        account = await accounts_service.update_account(
            db,
            household_id=principal.household_id,
            public_id=public_id,
            name=data.name,
            institution_public_id=data.institution_id,
            clear_institution=data.clear_institution,
            current_balance_minor=data.current_balance_minor,
        )
    except service.LedgerError as exc:
        raise _bad_request(exc) from exc
    await record_audit(
        db,
        action="account.update",
        household_id=principal.household_id,
        actor_user_id=principal.user_id,
        target_type="account",
        target_public_id=account.public_id,
    )
    await db.commit()
    (serialized,) = await _serialize_with_institutions(
        db, principal.household_id, [account]
    )
    return serialized


@router.post("/accounts/{public_id}/archive")
async def archive_account(
    public_id: str,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_principal),
    _csrf: None = Depends(csrf_guard),
) -> dict:
    return await _set_archived(db, principal, public_id, archived=True)


@router.post("/accounts/{public_id}/unarchive")
async def unarchive_account(
    public_id: str,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_principal),
    _csrf: None = Depends(csrf_guard),
) -> dict:
    return await _set_archived(db, principal, public_id, archived=False)


async def _set_archived(
    db: AsyncSession, principal: Principal, public_id: str, *, archived: bool
) -> dict:
    try:
        account = await accounts_service.set_archived(
            db,
            household_id=principal.household_id,
            public_id=public_id,
            archived=archived,
        )
    except service.LedgerError as exc:
        raise _bad_request(exc) from exc
    await record_audit(
        db,
        action="account.archive" if archived else "account.unarchive",
        household_id=principal.household_id,
        actor_user_id=principal.user_id,
        target_type="account",
        target_public_id=account.public_id,
    )
    await db.commit()
    (serialized,) = await _serialize_with_institutions(
        db, principal.household_id, [account]
    )
    return serialized


# --------------------------------------------------------------------------- #
# Transactions (manual add — T-021)
# --------------------------------------------------------------------------- #
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
        raise _bad_request(exc) from exc

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
