"""Insights HTTP routes (T-021) — the dashboard's data source.

Rewritten off the prototype's client-supplied ``user_id`` onto the canonical
schema + session Principal. No route accepts an identity parameter; the tenant
comes from the cookie session (SEC-01). Month windows are household-local
calendar months (FIN-03/04).
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi import status as http_status
from fastapi.exceptions import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.modules.identity.audit import record_audit
from app.modules.identity.deps import csrf_guard, require_principal
from app.modules.identity.models import Household
from app.modules.identity.service import Principal
from app.modules.insights import budgets as budget_svc
from app.modules.insights import service

router = APIRouter(prefix="/insights", tags=["Insights"])


async def _household_tz(db: AsyncSession, household_id: int) -> str:
    result = await db.execute(
        select(Household.timezone).where(Household.id == household_id)
    )
    return result.scalar_one_or_none() or "America/New_York"


@router.get("/spending-by-category")
async def spending_by_category(
    month_offset: int = Query(0, ge=0, le=24),
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_principal),
) -> dict:
    tz = await _household_tz(db, principal.household_id)
    return await service.spending_by_category(
        db, principal.household_id, month_offset, tz
    )


@router.get("/monthly-trends")
async def monthly_trends(
    months: int = Query(6, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_principal),
) -> dict:
    tz = await _household_tz(db, principal.household_id)
    return await service.monthly_trends(db, principal.household_id, months, tz)


@router.get("/cash-flow-summary")
async def cash_flow_summary(
    month_offset: int = Query(0, ge=0, le=24),
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_principal),
) -> dict:
    tz = await _household_tz(db, principal.household_id)
    return await service.cash_flow_summary(db, principal.household_id, month_offset, tz)


@router.get("/top-merchants")
async def top_merchants(
    month_offset: int = Query(0, ge=0, le=24),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_principal),
) -> dict:
    tz = await _household_tz(db, principal.household_id)
    return await service.top_merchants(
        db, principal.household_id, month_offset, tz, limit
    )


@router.get("/recent-transactions")
async def recent_transactions(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_principal),
) -> dict:
    return await service.recent_transactions(db, principal.household_id, limit)


# ── Budgets ───────────────────────────────────────────────────────────────────

@router.get("/budgets")
async def get_budgets(
    month: str | None = Query(None, description="YYYY-MM; defaults to current month"),
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_principal),
) -> dict:
    period = _parse_month(month, await _household_tz(db, principal.household_id))
    return await budget_svc.list_budgets(db, principal.household_id, period)


class BudgetUpsertInput(BaseModel):
    category_id: int
    amount_minor: int = Field(..., ge=0)
    month: str | None = Field(None, description="YYYY-MM; defaults to current month")


@router.put("/budgets")
async def upsert_budget(
    data: BudgetUpsertInput,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_principal),
    _csrf: None = Depends(csrf_guard),
) -> dict:
    period = _parse_month(data.month, await _household_tz(db, principal.household_id))
    try:
        budget = await budget_svc.upsert_budget(
            db,
            household_id=principal.household_id,
            category_id=data.category_id,
            period_month=period,
            amount_minor=data.amount_minor,
        )
    except budget_svc.BudgetError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    await record_audit(
        db,
        action="budget.upsert",
        household_id=principal.household_id,
        actor_user_id=principal.user_id,
        target_type="budget",
        target_public_id=None,
        metadata={"category_id": data.category_id, "month": period.strftime("%Y-%m")},
    )
    await db.commit()
    return {
        "status": "ok",
        "category_id": budget.category_id,
        "amount_minor": budget.amount_minor,
        "month": period.strftime("%Y-%m"),
    }


@router.get("/budget-alerts")
async def budget_alerts(
    month_offset: int = Query(0, ge=0, le=24),
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_principal),
) -> dict:
    tz = await _household_tz(db, principal.household_id)
    return await budget_svc.budget_alerts(db, principal.household_id, tz, month_offset)


def _parse_month(month: str | None, tz_name: str) -> date:
    if month is None:
        first, _, _ = service.month_bounds(tz_name, 0)
        return first
    try:
        year, mon = (int(x) for x in month.split("-"))
        return date(year, mon, 1)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="month must be formatted YYYY-MM",
        ) from exc
