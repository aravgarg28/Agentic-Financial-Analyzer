"""Insights + ledger correctness (T-021): FIN-03/04/05/08 regressions.

These use the model layer to arrange data at specific dates, then assert the
API returns calendar-month-correct, minor-unit-correct results.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date

from httpx import ASGITransport, AsyncClient

from app.modules.insights.service import month_bounds
from main import app
from tests.conftest import CSRF_HEADERS
from tests.helpers import add_account, add_category, add_transaction, make_household


@asynccontextmanager
async def _login(email: str, password: str = "a-strong-passphrase-1"):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers=CSRF_HEADERS,
    ) as client:
        r = await client.post(
            "/auth/login", json={"email": email, "password": password}
        )
        assert r.status_code == 200
        yield client


def test_month_bounds_are_calendar_months():
    """FIN-04: a 'month' is a real calendar month, not a 30-day window."""
    first, last, label = month_bounds("America/New_York", 0)
    assert first.day == 1
    assert last.day >= 28
    assert label == f"{first.year:04d}-{first.month:02d}"
    # Previous month is contiguous and distinct.
    pfirst, plast, _ = month_bounds("America/New_York", 1)
    assert plast.day >= 28
    assert (plast.year, plast.month) != (last.year, last.month)


async def test_cash_flow_uses_calendar_month_boundaries(seed_session):
    """FIN-03: current-month spend excludes last month's transactions."""
    _, mem = await make_household(seed_session, "cal@example.com")
    acct = await add_account(seed_session, mem.household_id)
    this_first, _, _ = month_bounds("America/New_York", 0)
    prev_first, _, _ = month_bounds("America/New_York", 1)

    # One expense this month, one last month.
    await add_transaction(
        seed_session,
        household_id=mem.household_id,
        account_id=acct.id,
        amount_minor=-2000,
        booked_date=this_first,
        description="this month",
    )
    await add_transaction(
        seed_session,
        household_id=mem.household_id,
        account_id=acct.id,
        amount_minor=-5000,
        booked_date=prev_first,
        description="last month",
    )
    await seed_session.commit()

    async with _login("cal@example.com") as c:
        this_month = (await c.get("/insights/cash-flow-summary")).json()
        last_month = (
            await c.get("/insights/cash-flow-summary", params={"month_offset": 1})
        ).json()
    assert this_month["expenses_minor"] == 2000
    assert last_month["expenses_minor"] == 5000


async def test_money_is_integer_minor_units_end_to_end(seed_session):
    """FIN-01: amounts are integer minor units through the API, no float."""
    _, mem = await make_household(seed_session, "money@example.com")
    acct = await add_account(seed_session, mem.household_id)
    await seed_session.commit()

    async with _login("money@example.com") as c:
        r = await c.post(
            "/ledger/transactions",
            json={
                "account_id": acct.public_id,
                "amount_minor": -12345,
                "booked_date": date.today().isoformat(),
                "description": "Widget",
            },
        )
        assert r.status_code == 201
        body = r.json()
        assert body["created"] is True
        assert body["amount_minor"] == -12345 and isinstance(body["amount_minor"], int)


async def test_spending_by_category_groups_including_uncategorized(seed_session):
    """spending-by-category must aggregate without a 500, including when some
    transactions have no category (NULL category_id). Regression: grouping by a
    parameterized coalesce() tripped Postgres' GROUP BY validation."""
    _, mem = await make_household(seed_session, "spend@example.com")
    acct = await add_account(seed_session, mem.household_id)
    cat = await add_category(seed_session, mem.household_id, "Groceries")
    this_first, _, _ = month_bounds("America/New_York", 0)

    await add_transaction(
        seed_session, household_id=mem.household_id, account_id=acct.id,
        amount_minor=-3000, booked_date=this_first, description="market",
        category_id=cat.id,
    )
    # No category → falls into the "Uncategorized" bucket.
    await add_transaction(
        seed_session, household_id=mem.household_id, account_id=acct.id,
        amount_minor=-1500, booked_date=this_first, description="misc",
    )
    await seed_session.commit()

    async with _login("spend@example.com") as c:
        r = await c.get("/insights/spending-by-category")
        assert r.status_code == 200
        data = {row["category"]: row["total_minor"] for row in r.json()["data"]}
    assert data["Groceries"] == 3000
    assert data["Uncategorized"] == 1500


async def test_manual_transaction_is_idempotent(seed_session):
    """FIN-05: re-posting the same transaction dedups instead of duplicating."""
    _, mem = await make_household(seed_session, "dedup@example.com")
    acct = await add_account(seed_session, mem.household_id)
    await seed_session.commit()

    payload = {
        "account_id": acct.public_id,
        "amount_minor": -700,
        "booked_date": date.today().isoformat(),
        "description": "Coffee",
    }
    async with _login("dedup@example.com") as c:
        first = await c.post("/ledger/transactions", json=payload)
        second = await c.post("/ledger/transactions", json=payload)
        assert first.json()["created"] is True
        assert second.json()["created"] is False
        assert first.json()["id"] == second.json()["id"]
        recent = (await c.get("/insights/recent-transactions")).json()["data"]
        assert len(recent) == 1


async def test_budget_upsert_is_rowcount_safe(seed_session):
    """FIN-08: budget upsert updates exactly one row and reads back correctly."""
    _, mem = await make_household(seed_session, "budget@example.com")
    cat = await add_category(seed_session, mem.household_id, "Dining")
    await seed_session.commit()

    async with _login("budget@example.com") as c:
        # Create.
        r1 = await c.put(
            "/insights/budgets",
            json={"category_id": cat.id, "amount_minor": 50000},
        )
        assert r1.status_code == 200
        # Update the same scope — must not create a duplicate.
        r2 = await c.put(
            "/insights/budgets",
            json={"category_id": cat.id, "amount_minor": 60000},
        )
        assert r2.status_code == 200
        listing = (await c.get("/insights/budgets")).json()["data"]
        assert len(listing) == 1
        assert listing[0]["amount_minor"] == 60000


async def test_budget_rejects_foreign_category(seed_session):
    """A budget cannot target a category from another household (SEC-01)."""
    _, mem_a = await make_household(seed_session, "ba@example.com")
    _, mem_b = await make_household(seed_session, "bb@example.com")
    cat_b = await add_category(seed_session, mem_b.household_id, "B-Only")
    await seed_session.commit()

    async with _login("ba@example.com") as c:
        r = await c.put(
            "/insights/budgets",
            json={"category_id": cat_b.id, "amount_minor": 1000},
        )
        assert r.status_code == 400
