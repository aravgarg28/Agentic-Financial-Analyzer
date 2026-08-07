"""Non-destructive demo seed (T-007, replaces the table-dropping prototype seed).

Creates ONE clearly-marked demo household with a demo user, a checking account,
system-style categories, ~90 days of realistic transactions, and a couple of
budgets — all through the normal model layer. Properties:

- **Never destructive.** No DROP/TRUNCATE/create_all; schema is owned by Alembic
  (run ``alembic upgrade head`` first). Fixes INF-01.
- **Refuses in production.** Aborts if ENVIRONMENT=production.
- **Idempotent.** Keyed off the demo user's email; a second run does nothing.
- **Random printed password.** No baked-in credentials (fixes SEC-06). The
  generated password is printed once to stdout for local login.

Run: ``python -m scripts.seed_demo`` (from the backend/ directory).
"""
from __future__ import annotations

import asyncio
import random
import secrets
from datetime import date, timedelta

from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.modules.identity import service
from app.modules.identity.models import User
from app.modules.ledger.models import Account, Category
from app.modules.ledger.service import compute_fingerprint, normalize_description

# Uses example.com — the IANA-reserved documentation domain. Note: reserved
# TLDs like .local/.test/.invalid are rejected by the API's email validator, so
# a demo user created with one of those could never log in (regression guard:
# test_seed_demo_email_is_api_loginable).
DEMO_EMAIL = "demo@example.com"

# (category name, type, [merchant samples], typical spend range in minor units)
CATEGORIES: list[tuple[str, str, list[str], tuple[int, int]]] = [
    ("Groceries", "expense", ["Whole Foods", "Trader Joe's", "Safeway"], (2000, 15000)),
    ("Dining", "expense", ["Chipotle", "Starbucks", "Local Diner"], (800, 6000)),
    ("Transport", "expense", ["Uber", "Shell", "Transit"], (500, 8000)),
    ("Shopping", "expense", ["Amazon", "Target", "Nike"], (1500, 25000)),
    ("Utilities", "expense", ["City Power", "Comcast", "Water Dept"], (4000, 20000)),
    ("Income", "income", ["Employer Payroll"], (250000, 250000)),
]


async def _already_seeded(session) -> bool:
    result = await session.execute(select(User.id).where(User.email == DEMO_EMAIL))
    return result.scalar_one_or_none() is not None


async def seed() -> None:
    if settings.is_production:
        raise SystemExit("Refusing to run the demo seed with ENVIRONMENT=production.")

    async with async_session() as session:
        if await _already_seeded(session):
            print(f"Demo data already present (user {DEMO_EMAIL}); nothing to do.")
            return

        password = secrets.token_urlsafe(12)
        user = await service.register_user(
            session, email=DEMO_EMAIL, password=password
        )
        await session.flush()
        membership = await service.load_membership(session, user.id)
        household_id = membership.household_id

        account = Account(
            household_id=household_id,
            name="Demo Checking",
            type="checking",
            tracking_mode="transactions",
            currency="USD",
            current_balance_minor=0,
        )
        session.add(account)
        await session.flush()

        cats: dict[str, Category] = {}
        for name, type_, _merchants, _rng in CATEGORIES:
            cat = Category(household_id=household_id, name=name, type=type_)
            session.add(cat)
            cats[name] = cat
        await session.flush()

        rng = random.Random(42)  # deterministic demo data
        today = date.today()
        for day_offset in range(90):
            booked = today - timedelta(days=day_offset)
            # A monthly salary on the 1st.
            if booked.day == 1:
                _add_tx(session, household_id, account.id, cats["Income"], 250000, booked, "Employer Payroll")
            # 0–3 expenses per day.
            for _ in range(rng.randint(0, 3)):
                name, _type, merchants, (lo, hi) = rng.choice(CATEGORIES[:-1])
                amount = -rng.randint(lo, hi)
                merchant = rng.choice(merchants)
                _add_tx(session, household_id, account.id, cats[name], amount, booked, merchant)

        # A couple of monthly budgets for the current month.
        from app.modules.insights.budgets import upsert_budget

        month_start = today.replace(day=1)
        await upsert_budget(
            session, household_id=household_id, category_id=cats["Groceries"].id,
            period_month=month_start, amount_minor=40000,
        )
        await upsert_budget(
            session, household_id=household_id, category_id=cats["Dining"].id,
            period_month=month_start, amount_minor=20000,
        )

        await session.commit()

    print("Demo data created.")
    print(f"  Login email:    {DEMO_EMAIL}")
    print(f"  Login password: {password}")
    print("  (This password is shown once. Re-run after deleting the demo user to rotate.)")


def _add_tx(session, household_id, account_id, category, amount_minor, booked, description):
    from app.modules.ledger.models import Transaction

    normalized = normalize_description(description)
    session.add(
        Transaction(
            household_id=household_id,
            account_id=account_id,
            amount_minor=amount_minor,
            currency="USD",
            booked_date=booked,
            status="posted",
            category_id=category.id,
            raw_description=description,
            normalized_description=normalized or None,
            source="manual",
            dedup_fingerprint=compute_fingerprint(
                account_id=account_id,
                booked_date=booked,
                amount_minor=amount_minor,
                normalized_desc=f"{normalized}:{secrets.token_hex(4)}",
            ),
        )
    )


if __name__ == "__main__":
    asyncio.run(seed())
