"""Read-only financial tools for the ReAct agent (T-030, canonical schema).

Hardening vs. the prototype:
- **No identity parameters (AGT-01).** Tools take only business filters; the
  household id comes from ``agent.context`` (server-injected), so a prompt-
  injected model can neither read another tenant's data nor pick a user_id.
- **No mutations (AGT-02).** The ``update_budget`` write tool is gone; every
  tool below is a pure read.
- **Bounded output (AGT-06).** Row counts are capped (``MAX_ROWS``) and the
  serialized result is truncated (``MAX_RESULT_CHARS``) so tool results cannot
  blow up the model context.

Money is returned in integer minor units (``*_minor``); the agent narrates and
is labelled beta until deterministic citations land in R3.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from langchain_core.tools import tool
from sqlalchemy import text

from app.agent.context import current_household_id
from app.database import async_session

MAX_ROWS = 50
MAX_RESULT_CHARS = 6000


def _cutoff(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


def _clamp_days(days: int) -> int:
    return max(1, min(days, 366))


def _dump(payload) -> str:
    """Serialize a tool result, enforcing the character cap (AGT-06)."""
    out = json.dumps(payload, default=str)
    if len(out) > MAX_RESULT_CHARS:
        return out[:MAX_RESULT_CHARS] + '... [truncated]"'
    return out


async def _run_query(sql: str, params: dict | None = None) -> list[dict]:
    async with async_session() as session:
        result = await session.execute(text(sql), params or {})
        columns = result.keys()
        return [dict(zip(columns, row, strict=False)) for row in result.fetchall()]


def _base_params(days: int) -> dict:
    """Tenant + time params. household_id is injected, never model-supplied."""
    return {"hid": current_household_id(), "cutoff": _cutoff(_clamp_days(days))}


@tool
async def query_transactions(
    category: str | None = None,
    merchant: str | None = None,
    min_amount_minor: int | None = None,
    max_amount_minor: int | None = None,
    days: int = 30,
    limit: int = 20,
) -> str:
    """Search the household's transactions with optional filters. Amounts are in
    minor units (cents); negative = expense. Returns matching transactions."""
    conditions = [
        "t.household_id = :hid",
        "t.deleted_at IS NULL",
        "t.booked_date >= :cutoff",
    ]
    params = _base_params(days)
    params["cutoff"] = params["cutoff"].date()
    if category:
        conditions.append("c.name ILIKE :category")
        params["category"] = category
    if merchant:
        conditions.append(
            "COALESCE(t.normalized_description, t.raw_description) ILIKE :merchant"
        )
        params["merchant"] = f"%{merchant.lower()}%"
    if min_amount_minor is not None:
        conditions.append("t.amount_minor >= :min_amt")
        params["min_amt"] = min_amount_minor
    if max_amount_minor is not None:
        conditions.append("t.amount_minor <= :max_amt")
        params["max_amt"] = max_amount_minor

    params["limit"] = max(1, min(limit, MAX_ROWS))
    sql = f"""
        SELECT t.public_id AS id,
               COALESCE(t.normalized_description, t.raw_description) AS description,
               t.amount_minor, t.currency, t.booked_date,
               COALESCE(c.name, 'Uncategorized') AS category
        FROM transactions t
        LEFT JOIN categories c ON c.id = t.category_id
        WHERE {" AND ".join(conditions)}
        ORDER BY t.booked_date DESC, t.id DESC
        LIMIT :limit
    """
    return _dump(await _run_query(sql, params))


@tool
async def get_spending_by_category(days: int = 30) -> str:
    """Total spending grouped by category over the last N days (minor units)."""
    params = _base_params(days)
    params["cutoff"] = params["cutoff"].date()
    sql = """
        SELECT COALESCE(c.name, 'Uncategorized') AS category,
               SUM(ABS(t.amount_minor)) AS total_minor,
               COUNT(*) AS count
        FROM transactions t
        LEFT JOIN categories c ON c.id = t.category_id
        WHERE t.household_id = :hid AND t.deleted_at IS NULL
          AND t.amount_minor < 0 AND t.booked_date >= :cutoff
        GROUP BY COALESCE(c.name, 'Uncategorized')
        ORDER BY total_minor DESC
        LIMIT :limit
    """
    params["limit"] = MAX_ROWS
    return _dump(await _run_query(sql, params))


@tool
async def get_monthly_trends(months: int = 6) -> str:
    """Spending and income per calendar month over the last N months (minor units)."""
    months = max(1, min(months, 24))
    params = {"hid": current_household_id(), "cutoff": (_cutoff(months * 31)).date()}
    sql = """
        SELECT TO_CHAR(booked_date, 'YYYY-MM') AS month,
               SUM(CASE WHEN amount_minor < 0 THEN ABS(amount_minor) ELSE 0 END) AS spending_minor,
               SUM(CASE WHEN amount_minor > 0 THEN amount_minor ELSE 0 END) AS income_minor
        FROM transactions
        WHERE household_id = :hid AND deleted_at IS NULL AND booked_date >= :cutoff
        GROUP BY month ORDER BY month
        LIMIT :limit
    """
    params["limit"] = MAX_ROWS
    return _dump(await _run_query(sql, params))


@tool
async def detect_anomalies(days: int = 30) -> str:
    """Flag unusually large expenses (> category mean + 2·stddev) in the window."""
    params = _base_params(days)
    params["cutoff"] = params["cutoff"].date()
    sql = """
        WITH cat_avg AS (
            SELECT category_id,
                   AVG(ABS(amount_minor)) AS avg_minor,
                   STDDEV(ABS(amount_minor)) AS std_minor
            FROM transactions
            WHERE household_id = :hid AND deleted_at IS NULL AND amount_minor < 0
            GROUP BY category_id
        )
        SELECT t.public_id AS id,
               COALESCE(t.normalized_description, t.raw_description) AS description,
               t.amount_minor, t.booked_date,
               COALESCE(c.name, 'Uncategorized') AS category,
               ROUND(ca.avg_minor) AS category_avg_minor
        FROM transactions t
        JOIN cat_avg ca ON COALESCE(t.category_id, -1) = COALESCE(ca.category_id, -1)
        LEFT JOIN categories c ON c.id = t.category_id
        WHERE t.household_id = :hid AND t.deleted_at IS NULL
          AND t.amount_minor < 0 AND t.booked_date >= :cutoff
          AND ABS(t.amount_minor) > ca.avg_minor + 2 * COALESCE(ca.std_minor, 0)
        ORDER BY ABS(t.amount_minor) DESC
        LIMIT :limit
    """
    params["limit"] = MAX_ROWS
    return _dump(await _run_query(sql, params))


@tool
async def get_merchant_analysis(days: int = 30, limit: int = 10) -> str:
    """Top payees by total spend over the last N days (minor units)."""
    params = _base_params(days)
    params["cutoff"] = params["cutoff"].date()
    params["limit"] = max(1, min(limit, MAX_ROWS))
    sql = """
        SELECT COALESCE(normalized_description, raw_description, '(unknown)') AS merchant,
               SUM(ABS(amount_minor)) AS total_minor,
               COUNT(*) AS visit_count
        FROM transactions
        WHERE household_id = :hid AND deleted_at IS NULL
          AND amount_minor < 0 AND booked_date >= :cutoff
        GROUP BY merchant
        ORDER BY total_minor DESC
        LIMIT :limit
    """
    return _dump(await _run_query(sql, params))


@tool
async def get_cash_flow_summary(days: int = 30) -> str:
    """Income vs. expenses and net cash flow over the last N days (minor units).
    This is a cash-flow summary over a period, not a net-worth balance."""
    params = _base_params(days)
    params["cutoff"] = params["cutoff"].date()
    sql = """
        SELECT
            COALESCE(SUM(CASE WHEN amount_minor > 0 THEN amount_minor ELSE 0 END), 0) AS income_minor,
            COALESCE(SUM(CASE WHEN amount_minor < 0 THEN ABS(amount_minor) ELSE 0 END), 0) AS expenses_minor,
            COALESCE(SUM(amount_minor), 0) AS net_minor,
            COUNT(*) AS transaction_count
        FROM transactions
        WHERE household_id = :hid AND deleted_at IS NULL AND booked_date >= :cutoff
    """
    rows = await _run_query(sql, params)
    return _dump(rows[0] if rows else {})


@tool
async def get_budgets() -> str:
    """List the household's budgets for the current calendar month (read-only,
    minor units). This tool cannot change budgets."""
    sql = """
        SELECT c.name AS category, b.amount_minor
        FROM budgets b
        JOIN categories c ON c.id = b.category_id
        WHERE b.household_id = :hid AND b.deleted_at IS NULL
          AND b.period_month = date_trunc('month', CURRENT_DATE)::date
        ORDER BY c.name
        LIMIT :limit
    """
    return _dump(await _run_query(sql, {"hid": current_household_id(), "limit": MAX_ROWS}))


# Read-only tool set only. No mutation tools are registered (AGT-02).
ALL_TOOLS = [
    query_transactions,
    get_spending_by_category,
    get_monthly_trends,
    detect_anomalies,
    get_merchant_analysis,
    get_cash_flow_summary,
    get_budgets,
]
