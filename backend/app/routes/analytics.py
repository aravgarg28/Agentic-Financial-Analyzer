"""
/analytics/* — REST endpoints that power the dashboard charts directly.
"""
from __future__ import annotations

import calendar
from datetime import datetime, timedelta

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import text

from app.database import async_session
from app.models import Transaction

router = APIRouter(prefix="/analytics", tags=["Analytics"])

def get_month_range(offset: int):
    now = datetime.utcnow()
    # Calculate target month and year
    month = now.month - offset
    year = now.year
    while month <= 0:
        month += 12
        year -= 1
    
    start_date = datetime(year, month, 1)
    # Last day of the month
    last_day = calendar.monthrange(year, month)[1]
    end_date = datetime(year, month, last_day, 23, 59, 59)
    return start_date, end_date


async def _q(sql: str, params: dict | None = None) -> list[dict]:
    async with async_session() as session:
        result = await session.execute(text(sql), params or {})
        return [dict(zip(result.keys(), row, strict=False)) for row in result.fetchall()]


@router.get("/spending-by-category")
async def spending_by_category(
    user_id: str = "user_1",
    month_offset: int = Query(0, ge=0, le=12),
):
    start_date, end_date = get_month_range(month_offset)
    rows = await _q(
        """
        SELECT category,
               ROUND(CAST(SUM(ABS(amount)) AS numeric), 2) as total,
               COUNT(*) as count
        FROM transactions
        WHERE user_id = :uid AND amount < 0 AND timestamp >= :start_date AND timestamp <= :end_date
        GROUP BY category ORDER BY total DESC
        """,
        {"uid": user_id, "start_date": start_date, "end_date": end_date},
    )
    return {"data": rows}


@router.get("/monthly-trends")
async def monthly_trends(
    user_id: str = "user_1",
    months: int = Query(6, ge=1, le=24),
):
    cutoff = datetime.utcnow() - timedelta(days=months * 30)
    rows = await _q(
        """
        SELECT TO_CHAR(timestamp, 'YYYY-MM') as month,
               ROUND(CAST(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) AS numeric), 2) as spending,
               ROUND(CAST(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) AS numeric), 2) as income
        FROM transactions
        WHERE user_id = :uid AND timestamp >= :cutoff
        GROUP BY month ORDER BY month
        """,
        {"uid": user_id, "cutoff": cutoff},
    )
    return {"data": rows}


@router.get("/net-worth")
async def net_worth(
    user_id: str = "user_1", 
    month_offset: int = Query(0, ge=0, le=12)
):
    start_date, end_date = get_month_range(month_offset)
    rows = await _q(
        """
        SELECT
            ROUND(CAST(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) AS numeric), 2) as total_income,
            ROUND(CAST(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) AS numeric), 2) as total_expenses,
            ROUND(CAST(SUM(amount) AS numeric), 2) as net_flow,
            COUNT(*) as total_transactions
        FROM transactions WHERE user_id = :uid AND timestamp >= :start_date AND timestamp <= :end_date
        """,
        {"uid": user_id, "start_date": start_date, "end_date": end_date},
    )
    return {"data": rows[0] if rows else {}}


@router.get("/top-merchants")
async def top_merchants(
    user_id: str = "user_1",
    month_offset: int = Query(0, ge=0, le=12),
    limit: int = Query(10, ge=1, le=50),
):
    start_date, end_date = get_month_range(month_offset)
    rows = await _q(
        """
        SELECT merchant,
               ROUND(CAST(SUM(ABS(amount)) AS numeric), 2) as total,
               COUNT(*) as visit_count
        FROM transactions
        WHERE user_id = :uid AND amount < 0 AND timestamp >= :start_date AND timestamp <= :end_date
        GROUP BY merchant ORDER BY total DESC LIMIT :lim
        """,
        {"uid": user_id, "start_date": start_date, "end_date": end_date, "lim": limit},
    )
    return {"data": rows}


@router.get("/budgets")
async def get_budgets(user_id: str = "user_1"):
    rows = await _q("SELECT category, amount FROM budgets WHERE user_id = :uid", {"uid": user_id})
    return {"data": {r["category"]: r["amount"] for r in rows}}

class BudgetUpdate(BaseModel):
    amount: float

@router.put("/budgets/{category}")
async def update_budget(category: str, b: BudgetUpdate, user_id: str = "user_1"):
    async with async_session() as session:
        await session.execute(
            text("UPDATE budgets SET amount = :amt WHERE user_id = :uid AND category = :cat"),
            {"amt": b.amount, "uid": user_id, "cat": category}
        )
        await session.commit()
    return {"status": "success", "category": category, "amount": b.amount}

@router.get("/budget-alerts")
async def budget_alerts(user_id: str = "user_1", days: int = Query(30, ge=1, le=365)):
    budget_rows = await _q("SELECT category, amount FROM budgets WHERE user_id = :uid", {"uid": user_id})
    budgets = {r["category"]: r["amount"] for r in budget_rows}
    
    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = await _q(
        """
        SELECT category, ROUND(CAST(SUM(ABS(amount)) AS numeric), 2) as total
        FROM transactions
        WHERE user_id = :uid AND amount < 0 AND timestamp >= :cutoff
        GROUP BY category
        """,
        {"uid": user_id, "cutoff": cutoff},
    )
    alerts = []
    for r in rows:
        b = budgets.get(r["category"])
        spent = float(r["total"])
        if b and spent > b:
            alerts.append({
                "category": r["category"], "spent": spent,
                "budget": b, "over_by": round(spent - b, 2),
            })
    alerts.sort(key=lambda x: x["over_by"], reverse=True)
    return {"data": alerts}


@router.get("/recent-transactions")
async def recent_transactions(
    user_id: str = "user_1",
    limit: int = Query(20, ge=1, le=100),
):
    rows = await _q(
        """
        SELECT id, merchant, amount, category, timestamp, description
        FROM transactions
        WHERE user_id = :uid
        ORDER BY timestamp DESC LIMIT :lim
        """,
        {"uid": user_id, "lim": limit},
    )
    for r in rows:
        if "timestamp" in r:
            r["timestamp"] = r["timestamp"].isoformat() if hasattr(r["timestamp"], "isoformat") else str(r["timestamp"])
    return {"data": rows}


class TransactionInput(BaseModel):
    merchant: str
    amount: float
    category: str
    description: str = ""

@router.post("/transactions")
async def add_transaction(tx: TransactionInput, user_id: str = "user_1"):
    async with async_session() as session:
        new_tx = Transaction(
            user_id=user_id,
            merchant=tx.merchant,
            amount=tx.amount,
            category=tx.category,
            description=tx.description,
            timestamp=datetime.utcnow()
        )
        session.add(new_tx)
        await session.commit()
        return {"status": "success", "id": new_tx.id}
