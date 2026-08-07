"""Insight calculators over the canonical ledger (T-021).

All money is computed in integer minor units and converted to a major-unit
decimal string only at the API boundary. All time windows are calendar months
resolved in the household's timezone (fixes FIN-03 UTC-boundary and FIN-04
30-day-"month" bugs). Every query is scoped by ``household_id`` supplied by the
server from the session — never by the client (SEC-01).

Sign convention: ``amount_minor < 0`` is an expense (money out), ``> 0`` income.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import Household
from app.modules.ledger.models import Category, Transaction

UNCATEGORIZED = "Uncategorized"


def month_bounds(tz_name: str, month_offset: int = 0) -> tuple[date, date, str]:
    """Return ``(first_day, last_day, 'YYYY-MM')`` for the household-local month
    ``month_offset`` months before the current one (0 = current month)."""
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("America/New_York")
    today = datetime.now(tz).date()
    year, month = today.year, today.month
    # Walk back month_offset months.
    month -= month_offset
    while month <= 0:
        month += 12
        year -= 1
    first = date(year, month, 1)
    last = date(year, month, monthrange(year, month)[1])
    return first, last, f"{year:04d}-{month:02d}"


async def _household_currency(session: AsyncSession, household_id: int) -> str:
    result = await session.execute(
        select(Household.base_currency).where(Household.id == household_id)
    )
    return result.scalar_one_or_none() or "USD"


async def spending_by_category(
    session: AsyncSession, household_id: int, month_offset: int, tz_name: str
) -> dict:
    first, last, label = month_bounds(tz_name, month_offset)
    stmt = (
        select(
            func.coalesce(Category.name, UNCATEGORIZED).label("category"),
            func.sum(func.abs(Transaction.amount_minor)).label("total_minor"),
            func.count().label("count"),
        )
        .select_from(Transaction)
        .outerjoin(Category, Category.id == Transaction.category_id)
        .where(
            Transaction.household_id == household_id,
            Transaction.deleted_at.is_(None),
            Transaction.amount_minor < 0,
            Transaction.booked_date >= first,
            Transaction.booked_date <= last,
        )
        # Group by the bare column (NULLs collapse into one group); the SELECT
        # coalesce is then well-defined per group. Grouping by the coalesce
        # expression itself trips Postgres (parameterized const in GROUP BY).
        .group_by(Category.name)
        .order_by(func.sum(func.abs(Transaction.amount_minor)).desc())
    )
    rows = (await session.execute(stmt)).all()
    currency = await _household_currency(session, household_id)
    return {
        "month": label,
        "currency": currency,
        "data": [
            {
                "category": r.category,
                "total_minor": int(r.total_minor),
                "count": int(r.count),
            }
            for r in rows
        ],
    }


async def monthly_trends(
    session: AsyncSession, household_id: int, months: int, tz_name: str
) -> dict:
    """Income/spending per calendar month for the last ``months`` months."""
    # Oldest month's first day is the lower bound.
    first_of_oldest, _, _ = month_bounds(tz_name, months - 1)
    _, last_of_current, _ = month_bounds(tz_name, 0)

    month_col = func.to_char(Transaction.booked_date, "YYYY-MM").label("month")
    stmt = (
        select(
            month_col,
            func.sum(func.abs(Transaction.amount_minor))
            .filter(Transaction.amount_minor < 0)
            .label("spending_minor"),
            func.sum(Transaction.amount_minor)
            .filter(Transaction.amount_minor > 0)
            .label("income_minor"),
        )
        .where(
            Transaction.household_id == household_id,
            Transaction.deleted_at.is_(None),
            Transaction.booked_date >= first_of_oldest,
            Transaction.booked_date <= last_of_current,
        )
        .group_by(month_col)
        .order_by(month_col)
    )
    rows = (await session.execute(stmt)).all()
    currency = await _household_currency(session, household_id)
    return {
        "currency": currency,
        "data": [
            {
                "month": r.month,
                "spending_minor": int(r.spending_minor or 0),
                "income_minor": int(r.income_minor or 0),
            }
            for r in rows
        ],
    }


async def cash_flow_summary(
    session: AsyncSession, household_id: int, month_offset: int, tz_name: str
) -> dict:
    """Income vs. expenses and net cash flow for one calendar month.

    Named 'cash flow', not 'net worth' — it is a flow over a period, not a
    balance (FIN-07). True net worth (account balances) is an R2 feature.
    """
    first, last, label = month_bounds(tz_name, month_offset)
    stmt = select(
        func.coalesce(
            func.sum(Transaction.amount_minor).filter(Transaction.amount_minor > 0), 0
        ).label("income_minor"),
        func.coalesce(
            func.sum(func.abs(Transaction.amount_minor)).filter(
                Transaction.amount_minor < 0
            ),
            0,
        ).label("expenses_minor"),
        func.coalesce(func.sum(Transaction.amount_minor), 0).label("net_minor"),
        func.count().label("count"),
    ).where(
        Transaction.household_id == household_id,
        Transaction.deleted_at.is_(None),
        Transaction.booked_date >= first,
        Transaction.booked_date <= last,
    )
    row = (await session.execute(stmt)).one()
    currency = await _household_currency(session, household_id)
    return {
        "month": label,
        "currency": currency,
        "income_minor": int(row.income_minor),
        "expenses_minor": int(row.expenses_minor),
        "net_minor": int(row.net_minor),
        "transaction_count": int(row.count),
    }


async def top_merchants(
    session: AsyncSession, household_id: int, month_offset: int, tz_name: str, limit: int
) -> dict:
    """Top payees by spend for a month. R0 groups by normalized_description
    (a dedicated merchant entity arrives in R1)."""
    first, last, label = month_bounds(tz_name, month_offset)
    payee = func.coalesce(
        Transaction.normalized_description, Transaction.raw_description, "(unknown)"
    ).label("merchant")
    stmt = (
        select(
            payee,
            func.sum(func.abs(Transaction.amount_minor)).label("total_minor"),
            func.count().label("visit_count"),
        )
        .where(
            Transaction.household_id == household_id,
            Transaction.deleted_at.is_(None),
            Transaction.amount_minor < 0,
            Transaction.booked_date >= first,
            Transaction.booked_date <= last,
        )
        .group_by(payee)
        .order_by(func.sum(func.abs(Transaction.amount_minor)).desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    currency = await _household_currency(session, household_id)
    return {
        "month": label,
        "currency": currency,
        "data": [
            {
                "merchant": r.merchant,
                "total_minor": int(r.total_minor),
                "visit_count": int(r.visit_count),
            }
            for r in rows
        ],
    }


async def recent_transactions(
    session: AsyncSession, household_id: int, limit: int
) -> dict:
    stmt = (
        select(
            Transaction.public_id,
            Transaction.amount_minor,
            Transaction.currency,
            Transaction.booked_date,
            func.coalesce(
                Transaction.normalized_description, Transaction.raw_description
            ).label("description"),
            func.coalesce(Category.name, UNCATEGORIZED).label("category"),
        )
        .select_from(Transaction)
        .outerjoin(Category, Category.id == Transaction.category_id)
        .where(
            Transaction.household_id == household_id,
            Transaction.deleted_at.is_(None),
        )
        .order_by(Transaction.booked_date.desc(), Transaction.id.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return {
        "data": [
            {
                "id": r.public_id,
                "amount_minor": int(r.amount_minor),
                "currency": r.currency,
                "booked_date": r.booked_date.isoformat(),
                "description": r.description,
                "category": r.category,
            }
            for r in rows
        ]
    }
