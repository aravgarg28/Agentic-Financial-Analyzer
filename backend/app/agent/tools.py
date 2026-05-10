"""
Eight financial analysis tools for the ReAct agent.
Each tool runs an async SQL query against the transactions table.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Optional

from langchain_core.tools import tool
from sqlalchemy import text

from app.database import async_session


# ── Helper ────────────────────────────────────────────────────────────────────

async def _run_query(sql: str, params: dict | None = None) -> list[dict]:
    """Execute a raw SQL query and return rows as dicts."""
    async with async_session() as session:
        result = await session.execute(text(sql), params or {})
        columns = result.keys()
        return [dict(zip(columns, row)) for row in result.fetchall()]


# ── Tool 1 — Query Transactions ──────────────────────────────────────────────

@tool
async def query_transactions(
    user_id: str = "user_1",
    category: Optional[str] = None,
    merchant: Optional[str] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    days: int = 30,
    limit: int = 20,
) -> str:
    """Search financial transactions with filters. Returns matching transactions.
    Use this when the user asks about specific transactions, purchases, or spending at a merchant."""
    conditions = ["user_id = :user_id"]
    params: dict = {"user_id": user_id}

    if category:
        conditions.append("category = :category")
        params["category"] = category
    if merchant:
        conditions.append("LOWER(merchant) LIKE LOWER(:merchant)")
        params["merchant"] = f"%{merchant}%"
    if min_amount is not None:
        conditions.append("amount >= :min_amount")
        params["min_amount"] = min_amount
    if max_amount is not None:
        conditions.append("amount <= :max_amount")
        params["max_amount"] = max_amount

    cutoff = datetime.utcnow() - timedelta(days=days)
    conditions.append("timestamp >= :cutoff")
    params["cutoff"] = cutoff

    where = " AND ".join(conditions)
    sql = f"SELECT * FROM transactions WHERE {where} ORDER BY timestamp DESC LIMIT :limit"
    params["limit"] = limit

    rows = await _run_query(sql, params)
    for r in rows:
        if "timestamp" in r and isinstance(r["timestamp"], datetime):
            r["timestamp"] = r["timestamp"].isoformat()
    return json.dumps(rows, default=str)


# ── Tool 2 — Spending by Category ────────────────────────────────────────────

@tool
async def get_spending_by_category(user_id: str = "user_1", days: int = 30) -> str:
    """Get total spending broken down by category for a time period.
    Use this when the user asks about spending breakdown or category analysis."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    sql = """
        SELECT category,
               ROUND(CAST(SUM(ABS(amount)) AS numeric), 2) as total,
               COUNT(*) as count
        FROM transactions
        WHERE user_id = :user_id AND amount < 0 AND timestamp >= :cutoff
        GROUP BY category
        ORDER BY total DESC
    """
    rows = await _run_query(sql, {"user_id": user_id, "cutoff": cutoff})
    return json.dumps(rows, default=str)


# ── Tool 3 — Monthly Trends ──────────────────────────────────────────────────

@tool
async def get_monthly_trends(user_id: str = "user_1", months: int = 6) -> str:
    """Get monthly spending and income trends.
    Use this when the user asks about trends over time or monthly comparisons."""
    cutoff = datetime.utcnow() - timedelta(days=months * 30)
    sql = """
        SELECT TO_CHAR(timestamp, 'YYYY-MM') as month,
               ROUND(CAST(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) AS numeric), 2) as spending,
               ROUND(CAST(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) AS numeric), 2) as income
        FROM transactions
        WHERE user_id = :user_id AND timestamp >= :cutoff
        GROUP BY month
        ORDER BY month
    """
    rows = await _run_query(sql, {"user_id": user_id, "cutoff": cutoff})
    return json.dumps(rows, default=str)


# ── Tool 4 — Detect Anomalies ────────────────────────────────────────────────

@tool
async def detect_anomalies(user_id: str = "user_1", days: int = 30) -> str:
    """Detect unusual or anomalous transactions (spending > 2x category average).
    Use this when the user asks about unusual charges or suspicious activity."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    sql = """
        WITH cat_avg AS (
            SELECT category, AVG(ABS(amount)) as avg_amount, STDDEV(ABS(amount)) as std_amount
            FROM transactions
            WHERE user_id = :user_id AND amount < 0
            GROUP BY category
        )
        SELECT t.id, t.merchant, t.amount, t.category, t.timestamp, t.description,
               ROUND(CAST(ca.avg_amount AS numeric), 2) as category_avg
        FROM transactions t
        JOIN cat_avg ca ON t.category = ca.category
        WHERE t.user_id = :user_id
          AND t.amount < 0
          AND t.timestamp >= :cutoff
          AND ABS(t.amount) > ca.avg_amount + 2 * COALESCE(ca.std_amount, 0)
        ORDER BY ABS(t.amount) DESC
        LIMIT 10
    """
    rows = await _run_query(sql, {"user_id": user_id, "cutoff": cutoff})
    for r in rows:
        if "timestamp" in r and isinstance(r["timestamp"], datetime):
            r["timestamp"] = r["timestamp"].isoformat()
    return json.dumps(rows, default=str)


# ── Tool 5 — Merchant Analysis ───────────────────────────────────────────────

@tool
async def get_merchant_analysis(user_id: str = "user_1", days: int = 30, limit: int = 10) -> str:
    """Get top merchants by total spending.
    Use this when the user asks about where they spend the most or merchant breakdowns."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    sql = """
        SELECT merchant,
               ROUND(CAST(SUM(ABS(amount)) AS numeric), 2) as total,
               COUNT(*) as visit_count,
               ROUND(CAST(AVG(ABS(amount)) AS numeric), 2) as avg_per_visit
        FROM transactions
        WHERE user_id = :user_id AND amount < 0 AND timestamp >= :cutoff
        GROUP BY merchant
        ORDER BY total DESC
        LIMIT :limit
    """
    rows = await _run_query(sql, {"user_id": user_id, "cutoff": cutoff, "limit": limit})
    return json.dumps(rows, default=str)


# ── Tool 6 — Net Worth Snapshot ───────────────────────────────────────────────

@tool
async def get_net_worth_snapshot(user_id: str = "user_1", days: int = 30) -> str:
    """Get a summary of income vs expenses and net cash flow.
    Use this when the user asks about their balance, savings, or overall financial health."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    sql = """
        SELECT
            ROUND(CAST(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) AS numeric), 2) as total_income,
            ROUND(CAST(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) AS numeric), 2) as total_expenses,
            ROUND(CAST(SUM(amount) AS numeric), 2) as net_flow,
            COUNT(*) as total_transactions
        FROM transactions
        WHERE user_id = :user_id AND timestamp >= :cutoff
    """
    rows = await _run_query(sql, {"user_id": user_id, "cutoff": cutoff})
    return json.dumps(rows[0] if rows else {}, default=str)


# ── Tool 7 — Financial Summary ───────────────────────────────────────────────

@tool
async def generate_financial_summary(user_id: str = "user_1", days: int = 30) -> str:
    """Generate a comprehensive financial summary including top categories, biggest expenses, and savings rate.
    Use this when the user asks for an overview or summary of their finances."""
    cutoff = datetime.utcnow() - timedelta(days=days)

    # Get net overview
    net_sql = """
        SELECT
            COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) as income,
            COALESCE(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END), 0) as expenses
        FROM transactions WHERE user_id = :user_id AND timestamp >= :cutoff
    """
    net = await _run_query(net_sql, {"user_id": user_id, "cutoff": cutoff})
    income = float(net[0]["income"]) if net else 0
    expenses = float(net[0]["expenses"]) if net else 0
    savings_rate = round((income - expenses) / income * 100, 1) if income > 0 else 0

    # Top 3 categories
    cat_sql = """
        SELECT category, ROUND(CAST(SUM(ABS(amount)) AS numeric), 2) as total
        FROM transactions
        WHERE user_id = :user_id AND amount < 0 AND timestamp >= :cutoff
        GROUP BY category ORDER BY total DESC LIMIT 3
    """
    top_cats = await _run_query(cat_sql, {"user_id": user_id, "cutoff": cutoff})

    # Biggest single expense
    big_sql = """
        SELECT merchant, amount, timestamp
        FROM transactions
        WHERE user_id = :user_id AND amount < 0 AND timestamp >= :cutoff
        ORDER BY amount ASC LIMIT 1
    """
    biggest = await _run_query(big_sql, {"user_id": user_id, "cutoff": cutoff})

    summary = {
        "period_days": days,
        "total_income": round(income, 2),
        "total_expenses": round(expenses, 2),
        "net_flow": round(income - expenses, 2),
        "savings_rate_pct": savings_rate,
        "top_categories": top_cats,
        "biggest_expense": biggest[0] if biggest else None,
    }
    for item in [summary.get("biggest_expense")]:
        if item and "timestamp" in item and isinstance(item["timestamp"], datetime):
            item["timestamp"] = item["timestamp"].isoformat()

    return json.dumps(summary, default=str)


# ── Tool 8 — Budget Alert ────────────────────────────────────────────────────

@tool
async def budget_alert(user_id: str = "user_1", days: int = 30) -> str:
    """Check if spending in any category exceeds typical budget thresholds.
    Use this when the user asks about budget, overspending, or wants alerts."""
    # Default monthly budgets
    budgets = {
        "food": 500, "transport": 300, "shopping": 400,
        "utilities": 250, "entertainment": 100, "health": 200,
        "travel": 500,
    }
    cutoff = datetime.utcnow() - timedelta(days=days)
    sql = """
        SELECT category, ROUND(CAST(SUM(ABS(amount)) AS numeric), 2) as total
        FROM transactions
        WHERE user_id = :user_id AND amount < 0 AND timestamp >= :cutoff
        GROUP BY category
    """
    rows = await _run_query(sql, {"user_id": user_id, "cutoff": cutoff})

    alerts = []
    for row in rows:
        cat = row["category"]
        spent = float(row["total"])
        budget = budgets.get(cat)
        if budget and spent > budget:
            alerts.append({
                "category": cat,
                "spent": spent,
                "budget": budget,
                "over_by": round(spent - budget, 2),
                "pct_over": round((spent - budget) / budget * 100, 1),
            })
    alerts.sort(key=lambda x: x["over_by"], reverse=True)
    return json.dumps(alerts, default=str)


# ── Export all tools ──────────────────────────────────────────────────────────

ALL_TOOLS = [
    query_transactions,
    get_spending_by_category,
    get_monthly_trends,
    detect_anomalies,
    get_merchant_analysis,
    get_net_worth_snapshot,
    generate_financial_summary,
    budget_alert,
]
