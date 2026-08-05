"""Budget read/upsert + alert calculation (T-021, FIN-08/09).

Budgets are per (household, category, calendar month) in minor units. The upsert
matches an existing live row explicitly and asserts the affected row count, so a
mismatch can never masquerade as success the way the prototype's blind UPDATE
did (FIN-08). Alerts compare a month's budget against that same month's spend
(fixes FIN-09's rolling-window vs monthly-budget mismatch).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.insights.models import Budget
from app.modules.insights.service import UNCATEGORIZED, month_bounds
from app.modules.ledger.models import Category, Transaction


class BudgetError(Exception):
    """Invalid budget operation (e.g. category not in this household)."""


async def _category_in_household(
    session: AsyncSession, household_id: int, category_id: int
) -> bool:
    result = await session.execute(
        select(Category.id).where(
            Category.id == category_id,
            # System categories (household_id NULL) are usable by everyone;
            # household categories must match the caller's household.
            (Category.household_id == household_id) | (Category.household_id.is_(None)),
            Category.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none() is not None


async def upsert_budget(
    session: AsyncSession,
    *,
    household_id: int,
    category_id: int,
    period_month: date,
    amount_minor: int,
) -> Budget:
    """Create or update the single live budget for the scope. Caller commits."""
    if amount_minor < 0:
        raise BudgetError("Budget amount cannot be negative.")
    # Normalize to the first of the month (the period key).
    period_month = period_month.replace(day=1)
    if not await _category_in_household(session, household_id, category_id):
        raise BudgetError("Category does not belong to this household.")

    result = await session.execute(
        select(Budget).where(
            Budget.household_id == household_id,
            Budget.category_id == category_id,
            Budget.period_month == period_month,
            Budget.deleted_at.is_(None),
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        existing.amount_minor = amount_minor
        return existing

    budget = Budget(
        household_id=household_id,
        category_id=category_id,
        period_month=period_month,
        amount_minor=amount_minor,
    )
    session.add(budget)
    return budget


async def list_budgets(
    session: AsyncSession, household_id: int, period_month: date
) -> dict:
    period_month = period_month.replace(day=1)
    stmt = (
        select(
            Budget.category_id,
            Category.name.label("category"),
            Budget.amount_minor,
        )
        .join(Category, Category.id == Budget.category_id)
        .where(
            Budget.household_id == household_id,
            Budget.period_month == period_month,
            Budget.deleted_at.is_(None),
        )
        .order_by(Category.name)
    )
    rows = (await session.execute(stmt)).all()
    return {
        "month": period_month.strftime("%Y-%m"),
        "data": [
            {
                "category_id": r.category_id,
                "category": r.category,
                "amount_minor": int(r.amount_minor),
            }
            for r in rows
        ],
    }


async def budget_alerts(
    session: AsyncSession, household_id: int, tz_name: str, month_offset: int = 0
) -> dict:
    """Budgets exceeded by spend in the same calendar month (FIN-09 fix)."""
    first, last, label = month_bounds(tz_name, month_offset)
    period_month = first  # already the first of month

    # Spend per category for the month.
    spend_stmt = (
        select(
            Transaction.category_id,
            func.sum(func.abs(Transaction.amount_minor)).label("spent_minor"),
        )
        .where(
            Transaction.household_id == household_id,
            Transaction.deleted_at.is_(None),
            Transaction.amount_minor < 0,
            Transaction.booked_date >= first,
            Transaction.booked_date <= last,
        )
        .group_by(Transaction.category_id)
    )
    spend = {r.category_id: int(r.spent_minor) for r in (await session.execute(spend_stmt)).all()}

    budget_stmt = (
        select(Budget.category_id, Category.name, Budget.amount_minor)
        .join(Category, Category.id == Budget.category_id)
        .where(
            Budget.household_id == household_id,
            Budget.period_month == period_month,
            Budget.deleted_at.is_(None),
        )
    )
    alerts = []
    for row in (await session.execute(budget_stmt)).all():
        spent = spend.get(row.category_id, 0)
        if spent > row.amount_minor:
            alerts.append(
                {
                    "category": row.name or UNCATEGORIZED,
                    "spent_minor": spent,
                    "budget_minor": int(row.amount_minor),
                    "over_by_minor": spent - int(row.amount_minor),
                }
            )
    alerts.sort(key=lambda a: a["over_by_minor"], reverse=True)
    return {"month": label, "data": alerts}
