"""
/analytics/* — REST endpoints that power the dashboard charts directly.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Query
from sqlalchemy import text

from app.database import async_session

router = APIRouter(prefix="/analytics", tags=["Analytics"])


async def _q(sql: str, params: dict | None = None) -> list[dict]:
    async with async_session() as session:
        result = await session.execute(text(sql), params or {})
        return [dict(zip(result.keys(), row)) for row in result.fetchall()]


@router.get("/spending-by-category")
async def spending_by_category(
    user_id: str = "user_1",
    days: int = Query(30, ge=1, le=365),
):
    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = await _q(
        """
        SELECT category,
               ROUND(CAST(SUM(ABS(amount)) AS numeric), 2) as total,
               COUNT(*) as count
        FROM transactions
        WHERE user_id = :uid AND amount < 0 AND timestamp >= :cutoff
        GROUP BY category ORDER BY total DESC
        """,
        {"uid": user_id, "cutoff": cutoff},
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
async def net_worth(user_id: str = "user_1", days: int = Query(30, ge=1, le=365)):
    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = await _q(
        """
        SELECT
            ROUND(CAST(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) AS numeric), 2) as total_income,
            ROUND(CAST(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) AS numeric), 2) as total_expenses,
            ROUND(CAST(SUM(amount) AS numeric), 2) as net_flow,
            COUNT(*) as total_transactions
        FROM transactions WHERE user_id = :uid AND timestamp >= :cutoff
        """,
        {"uid": user_id, "cutoff": cutoff},
    )
    return {"data": rows[0] if rows else {}}


@router.get("/top-merchants")
async def top_merchants(
    user_id: str = "user_1",
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(10, ge=1, le=50),
):
    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = await _q(
        """
        SELECT merchant,
               ROUND(CAST(SUM(ABS(amount)) AS numeric), 2) as total,
               COUNT(*) as visit_count
        FROM transactions
        WHERE user_id = :uid AND amount < 0 AND timestamp >= :cutoff
        GROUP BY merchant ORDER BY total DESC LIMIT :lim
        """,
        {"uid": user_id, "cutoff": cutoff, "lim": limit},
    )
    return {"data": rows}


@router.get("/budget-alerts")
async def budget_alerts(user_id: str = "user_1", days: int = Query(30, ge=1, le=365)):
    budgets = {
        "food": 500, "transport": 300, "shopping": 400,
        "utilities": 250, "entertainment": 100, "health": 200,
        "travel": 500,
    }
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
