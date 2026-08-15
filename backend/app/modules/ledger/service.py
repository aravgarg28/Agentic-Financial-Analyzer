"""Ledger service (T-021 slice): manual transaction creation with dedup.

Full ledger CRUD (edit, list-with-filters, merchant entity) is R1 (T-061); R0
provides the account-scoped manual add the dashboard needs, on the canonical
minor-units schema. A stable fingerprint gives us idempotency now and feeds the
import dedup engine later (FIN-05).
"""
from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass
from datetime import date

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ledger.models import Account, Category, Merchant, Transaction


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

    merchant = await resolve_or_create_merchant(session, household_id, normalized)
    tx = Transaction(
        household_id=household_id,
        account_id=account.id,
        merchant_id=merchant.id if merchant else None,
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
    await _recompute_balance(session, account)
    return tx, True


async def resolve_or_create_merchant(
    session: AsyncSession, household_id: int, normalized_desc: str
) -> Merchant | None:
    """Resolve (or create) the merchant for a normalized description. Returns
    None for an empty description. Handles the create race by re-querying."""
    if not normalized_desc:
        return None
    result = await session.execute(
        select(Merchant).where(
            Merchant.household_id == household_id,
            Merchant.canonical_name == normalized_desc,
        )
    )
    merchant = result.scalar_one_or_none()
    if merchant is not None:
        return merchant
    merchant = Merchant(
        household_id=household_id,
        canonical_name=normalized_desc,
        raw_pattern=normalized_desc,
    )
    session.add(merchant)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        result = await session.execute(
            select(Merchant).where(
                Merchant.household_id == household_id,
                Merchant.canonical_name == normalized_desc,
            )
        )
        return result.scalar_one()
    return merchant


async def _recompute_balance(session: AsyncSession, account: Account) -> None:
    """Refresh a transactions-mode account's cached balance after a mutation.
    Imported lazily to avoid a service<->accounts import cycle."""
    from app.modules.ledger.accounts import recompute_account_balance

    await recompute_account_balance(session, account)


# Sentinel so edit callers can distinguish "leave field unchanged" from "set to
# None" for nullable fields (category, description).
_UNSET = object()


async def edit_transaction(
    session: AsyncSession,
    *,
    household_id: int,
    public_id: str,
    amount_minor: int | None = None,
    booked_date: date | None = None,
    raw_description=_UNSET,
    category_id=_UNSET,
) -> Transaction:
    """Edit a transaction's amount/date/description/category. Recomputes the
    dedup fingerprint and merchant link when identity fields change, and the
    account's cached balance when the amount changes. Caller commits."""
    tx = await resolve_transaction(session, household_id, public_id)

    identity_changed = False
    if amount_minor is not None and amount_minor != tx.amount_minor:
        tx.amount_minor = amount_minor
        identity_changed = True
    if booked_date is not None and booked_date != tx.booked_date:
        tx.booked_date = booked_date
        identity_changed = True
    if raw_description is not _UNSET:
        normalized = normalize_description(raw_description)
        tx.raw_description = raw_description
        tx.normalized_description = normalized or None
        merchant = await resolve_or_create_merchant(session, household_id, normalized)
        tx.merchant_id = merchant.id if merchant else None
        identity_changed = True
    if category_id is not _UNSET:
        tx.category_id = await resolve_category_id(session, household_id, category_id)

    if identity_changed:
        tx.dedup_fingerprint = compute_fingerprint(
            account_id=tx.account_id,
            booked_date=tx.booked_date,
            amount_minor=tx.amount_minor,
            normalized_desc=tx.normalized_description or "",
        )
    await session.flush()

    account = await session.get(Account, tx.account_id)
    if account is not None:
        await _recompute_balance(session, account)
    return tx


async def soft_delete_transaction(
    session: AsyncSession, *, household_id: int, public_id: str
) -> Transaction:
    """Soft-delete a transaction (sets deleted_at) and refresh the account
    balance so the deleted amount stops counting. Caller commits."""
    from datetime import UTC, datetime

    tx = await resolve_transaction(session, household_id, public_id)
    tx.deleted_at = datetime.now(UTC)
    await session.flush()
    account = await session.get(Account, tx.account_id)
    if account is not None:
        await _recompute_balance(session, account)
    return tx


# --------------------------------------------------------------------------- #
# Listing with filters + stable cursor pagination
# --------------------------------------------------------------------------- #
@dataclass
class TransactionFilters:
    account_public_id: str | None = None
    category_id: int | None = None
    uncategorized: bool = False
    start_date: date | None = None
    end_date: date | None = None
    min_amount_minor: int | None = None
    max_amount_minor: int | None = None
    search: str | None = None


def _encode_cursor(booked: date, row_id: int) -> str:
    return base64.urlsafe_b64encode(f"{booked.isoformat()}|{row_id}".encode()).decode()


def _decode_cursor(cursor: str) -> tuple[date, int]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        date_str, id_str = raw.split("|", 1)
        return date.fromisoformat(date_str), int(id_str)
    except (ValueError, TypeError) as exc:
        raise LedgerError("Invalid pagination cursor.") from exc


async def list_transactions(
    session: AsyncSession,
    household_id: int,
    *,
    filters: TransactionFilters,
    limit: int = 50,
    cursor: str | None = None,
) -> tuple[list[Transaction], str | None]:
    """Return (transactions, next_cursor). Ordered by (booked_date, id) DESC so
    the cursor is stable under concurrent inserts — a page already fetched never
    shifts when newer rows arrive."""
    limit = max(1, min(limit, 200))
    conditions = [
        Transaction.household_id == household_id,
        Transaction.deleted_at.is_(None),
    ]
    if filters.account_public_id:
        account = await resolve_account(session, household_id, filters.account_public_id)
        conditions.append(Transaction.account_id == account.id)
    if filters.uncategorized:
        conditions.append(Transaction.category_id.is_(None))
    elif filters.category_id is not None:
        conditions.append(Transaction.category_id == filters.category_id)
    if filters.start_date is not None:
        conditions.append(Transaction.booked_date >= filters.start_date)
    if filters.end_date is not None:
        conditions.append(Transaction.booked_date <= filters.end_date)
    if filters.min_amount_minor is not None:
        conditions.append(Transaction.amount_minor >= filters.min_amount_minor)
    if filters.max_amount_minor is not None:
        conditions.append(Transaction.amount_minor <= filters.max_amount_minor)
    if filters.search:
        needle = f"%{filters.search.lower()}%"
        conditions.append(
            func.coalesce(
                Transaction.normalized_description, Transaction.raw_description
            ).ilike(needle)
        )
    if cursor:
        c_date, c_id = _decode_cursor(cursor)
        conditions.append(
            or_(
                Transaction.booked_date < c_date,
                and_(Transaction.booked_date == c_date, Transaction.id < c_id),
            )
        )

    stmt = (
        select(Transaction)
        .where(*conditions)
        .order_by(Transaction.booked_date.desc(), Transaction.id.desc())
        .limit(limit + 1)  # fetch one extra to detect a next page
    )
    rows = list((await session.execute(stmt)).scalars().all())
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = _encode_cursor(last.booked_date, last.id)
    return rows, next_cursor
