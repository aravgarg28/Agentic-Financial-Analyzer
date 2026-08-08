"""Ledger service (T-021 slice): manual transaction creation with dedup.

Full ledger CRUD (edit, list-with-filters, merchant entity) is R1 (T-061); R0
provides the account-scoped manual add the dashboard needs, on the canonical
minor-units schema. A stable fingerprint gives us idempotency now and feeds the
import dedup engine later (FIN-05).
"""
from __future__ import annotations

import hashlib
import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ledger.models import Account, Category, Transaction


class LedgerError(Exception):
    """Invalid ledger operation (unknown account/category, etc.)."""


_WS = re.compile(r"\s+")


def normalize_description(raw: str | None) -> str:
    """Lowercase, collapse whitespace, strip. Used for display grouping and as
    a fingerprint input so trivially different strings dedup together."""
    if not raw:
        return ""
    return _WS.sub(" ", raw.strip().lower())


def compute_fingerprint(
    *, account_id: int, booked_date: date, amount_minor: int, normalized_desc: str
) -> str:
    """Deterministic dedup key over the fields that identify a transaction
    (FIN-05). Same across re-imports of the same row."""
    basis = f"{account_id}|{booked_date.isoformat()}|{amount_minor}|{normalized_desc}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


async def resolve_account(
    session: AsyncSession, household_id: int, account_public_id: str
) -> Account:
    """Look up an account by public id within the caller's household.

    Scoping the query by household_id is the tenant-isolation guarantee: an id
    from another household simply does not match (SEC-01)."""
    result = await session.execute(
        select(Account).where(
            Account.public_id == account_public_id,
            Account.household_id == household_id,
            Account.deleted_at.is_(None),
        )
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise LedgerError("Account not found.")
    return account


async def resolve_transaction(
    session: AsyncSession, household_id: int, public_id: str
) -> Transaction:
    """Look up a live transaction by public id within the caller's household."""
    result = await session.execute(
        select(Transaction).where(
            Transaction.public_id == public_id,
            Transaction.household_id == household_id,
            Transaction.deleted_at.is_(None),
        )
    )
    tx = result.scalar_one_or_none()
    if tx is None:
        raise LedgerError("Transaction not found.")
    return tx


async def resolve_category_id(
    session: AsyncSession, household_id: int, category_id: int | None
) -> int | None:
    if category_id is None:
        return None
    result = await session.execute(
        select(Category.id).where(
            Category.id == category_id,
            (Category.household_id == household_id) | (Category.household_id.is_(None)),
            Category.deleted_at.is_(None),
        )
    )
    if result.scalar_one_or_none() is None:
        raise LedgerError("Category not found.")
    return category_id


async def add_manual_transaction(
    session: AsyncSession,
    *,
    household_id: int,
    account_public_id: str,
    amount_minor: int,
    booked_date: date,
    raw_description: str | None,
    category_id: int | None,
) -> tuple[Transaction, bool]:
    """Add a manual transaction. Returns ``(transaction, created)``.

    If a live transaction with the same fingerprint already exists, it is
    returned with ``created=False`` (idempotent — FIN-05) instead of inserting
    a duplicate. Caller commits.
    """
    account = await resolve_account(session, household_id, account_public_id)
    resolved_category = await resolve_category_id(session, household_id, category_id)

    normalized = normalize_description(raw_description)
    fingerprint = compute_fingerprint(
        account_id=account.id,
        booked_date=booked_date,
        amount_minor=amount_minor,
        normalized_desc=normalized,
    )

    existing = await session.execute(
        select(Transaction).where(
            Transaction.household_id == household_id,
            Transaction.account_id == account.id,
            Transaction.dedup_fingerprint == fingerprint,
            Transaction.deleted_at.is_(None),
        )
    )
    dup = existing.scalar_one_or_none()
    if dup is not None:
        return dup, False

    tx = Transaction(
        household_id=household_id,
        account_id=account.id,
        amount_minor=amount_minor,
        currency=account.currency,
        booked_date=booked_date,
        status="posted",
        category_id=resolved_category,
        raw_description=raw_description,
        normalized_description=normalized or None,
        source="manual",
        dedup_fingerprint=fingerprint,
    )
    session.add(tx)
    await session.flush()
    return tx, True
