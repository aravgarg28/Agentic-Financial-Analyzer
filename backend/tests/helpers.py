"""Test helpers for arranging tenant data directly through the model layer."""
from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity import service
from app.modules.ledger.models import Account, Category, Transaction
from app.modules.ledger.service import compute_fingerprint, normalize_description


async def make_household(
    session: AsyncSession, email: str, password: str = "a-strong-passphrase-1"
):
    """Register a user + household and return (user, membership)."""
    user = await service.register_user(session, email=email, password=password)
    await session.flush()
    membership = await service.load_membership(session, user.id)
    return user, membership


async def add_account(
    session: AsyncSession, household_id: int, name: str = "Checking", currency: str = "USD"
) -> Account:
    account = Account(
        household_id=household_id,
        name=name,
        type="checking",
        tracking_mode="transactions",
        currency=currency,
    )
    session.add(account)
    await session.flush()
    return account


async def add_category(
    session: AsyncSession, household_id: int | None, name: str, type_: str = "expense"
) -> Category:
    cat = Category(household_id=household_id, name=name, type=type_)
    session.add(cat)
    await session.flush()
    return cat


async def add_transaction(
    session: AsyncSession,
    *,
    household_id: int,
    account_id: int,
    amount_minor: int,
    booked_date: date,
    description: str = "Test",
    category_id: int | None = None,
) -> Transaction:
    normalized = normalize_description(description)
    tx = Transaction(
        household_id=household_id,
        account_id=account_id,
        amount_minor=amount_minor,
        currency="USD",
        booked_date=booked_date,
        status="posted",
        category_id=category_id,
        raw_description=description,
        normalized_description=normalized or None,
        source="manual",
        dedup_fingerprint=compute_fingerprint(
            account_id=account_id,
            booked_date=booked_date,
            amount_minor=amount_minor,
            normalized_desc=normalized,
        ),
    )
    session.add(tx)
    await session.flush()
    return tx
