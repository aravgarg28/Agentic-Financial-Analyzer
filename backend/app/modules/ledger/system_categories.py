"""Canonical system-default category taxonomy (T-062).

Single source of truth for the shared, read-only categories (household_id NULL,
is_system) every household starts with. The Alembic data migration seeds these
into real databases; ``ensure_system_categories`` seeds them at runtime (used by
the test harness, which builds its schema with ``create_all`` rather than
migrations, and available for any bootstrap that needs them).

Changing this list does NOT retroactively update databases that already ran the
seeding migration — add a new migration for that. Fresh databases and tests pick
up the current list.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ledger.models import Category

# (name, type) — flat, top-level system categories; users add 2-level children.
SYSTEM_CATEGORIES: list[tuple[str, str]] = [
    # Income
    ("Salary", "income"),
    ("Interest", "income"),
    ("Refunds", "income"),
    ("Other Income", "income"),
    # Expense
    ("Groceries", "expense"),
    ("Dining", "expense"),
    ("Transport", "expense"),
    ("Shopping", "expense"),
    ("Housing", "expense"),
    ("Utilities", "expense"),
    ("Health", "expense"),
    ("Insurance", "expense"),
    ("Entertainment", "expense"),
    ("Travel", "expense"),
    ("Education", "expense"),
    ("Subscriptions", "expense"),
    ("Personal Care", "expense"),
    ("Fees & Charges", "expense"),
    ("Gifts & Donations", "expense"),
    ("Other Expense", "expense"),
    # Transfer
    ("Transfer", "transfer"),
    ("Credit Card Payment", "transfer"),
]


async def ensure_system_categories(session: AsyncSession) -> int:
    """Idempotently insert any missing system categories. Returns how many were
    added. Caller commits."""
    existing = set(
        (
            await session.execute(
                select(Category.name).where(
                    Category.household_id.is_(None), Category.is_system.is_(True)
                )
            )
        )
        .scalars()
        .all()
    )
    added = 0
    for name, type_ in SYSTEM_CATEGORIES:
        if name in existing:
            continue
        session.add(
            Category(household_id=None, parent_id=None, name=name, type=type_, is_system=True)
        )
        added += 1
    if added:
        await session.flush()
    return added
