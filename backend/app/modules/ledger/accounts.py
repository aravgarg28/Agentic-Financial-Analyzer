"""Accounts & institutions service (T-060).

Household-scoped CRUD for accounts and their (optional) institution labels.
Money stays in integer minor units. The current-balance cache is derived for
transactions-mode accounts (sum of live transactions) and user-set for
balance-only accounts (D10) — recompute_account_balance is the single hook the
ledger calls after any transaction mutation (wired fully in T-061).
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import Household
from app.modules.ledger.models import Account, Institution, Transaction
from app.modules.ledger.service import LedgerError

ACCOUNT_TYPES = frozenset(
    {
        "checking",
        "savings",
        "credit_card",
        "loan",
        "investment",
        "property",
        "cash",
        "other",
    }
)
TRACKING_MODES = frozenset({"transactions", "balance_only"})


def _validate_currency(currency: str) -> str:
    code = currency.strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise LedgerError("Currency must be a 3-letter ISO-4217 code.")
    return code


async def _household_currency(session: AsyncSession, household_id: int) -> str:
    result = await session.execute(
        select(Household.base_currency).where(Household.id == household_id)
    )
    return result.scalar_one_or_none() or "USD"


# --------------------------------------------------------------------------- #
# Institutions
# --------------------------------------------------------------------------- #
async def create_institution(
    session: AsyncSession, *, household_id: int, name: str, kind: str | None = None
) -> Institution:
    clean = name.strip()
    if not clean:
        raise LedgerError("Institution name is required.")
    inst = Institution(household_id=household_id, name=clean, kind=kind)
    session.add(inst)
    try:
        await session.flush()
    except IntegrityError as exc:  # unique (household_id, name) violation
        await session.rollback()
        raise LedgerError("An institution with that name already exists.") from exc
    return inst


async def list_institutions(
    session: AsyncSession, household_id: int
) -> list[Institution]:
    result = await session.execute(
        select(Institution)
        .where(
            Institution.household_id == household_id,
            Institution.deleted_at.is_(None),
        )
        .order_by(Institution.name)
    )
    return list(result.scalars().all())


async def resolve_institution(
    session: AsyncSession, household_id: int, public_id: str
) -> Institution:
    result = await session.execute(
        select(Institution).where(
            Institution.public_id == public_id,
            Institution.household_id == household_id,
            Institution.deleted_at.is_(None),
        )
    )
    inst = result.scalar_one_or_none()
    if inst is None:
        raise LedgerError("Institution not found.")
    return inst


# --------------------------------------------------------------------------- #
# Accounts
# --------------------------------------------------------------------------- #
async def create_account(
    session: AsyncSession,
    *,
    household_id: int,
    name: str,
    type: str,
    tracking_mode: str,
    currency: str | None = None,
    institution_public_id: str | None = None,
    opening_balance_minor: int | None = None,
) -> Account:
    clean_name = name.strip()
    if not clean_name:
        raise LedgerError("Account name is required.")
    if type not in ACCOUNT_TYPES:
        raise LedgerError(f"Invalid account type: {type!r}.")
    if tracking_mode not in TRACKING_MODES:
        raise LedgerError(f"Invalid tracking mode: {tracking_mode!r}.")

    resolved_currency = (
        _validate_currency(currency)
        if currency
        else await _household_currency(session, household_id)
    )

    institution_id: int | None = None
    if institution_public_id:
        inst = await resolve_institution(session, household_id, institution_public_id)
        institution_id = inst.id

    # For a fresh account with no transactions yet, the derived balance equals
    # its opening balance (0 if unspecified). balance-only accounts keep whatever
    # the user provides; transactions-mode accounts get recomputed as rows land.
    balance = opening_balance_minor if opening_balance_minor is not None else 0

    account = Account(
        household_id=household_id,
        institution_id=institution_id,
        name=clean_name,
        type=type,
        tracking_mode=tracking_mode,
        currency=resolved_currency,
        current_balance_minor=balance,
    )
    session.add(account)
    await session.flush()
    return account


async def get_account(
    session: AsyncSession, household_id: int, public_id: str, *, include_archived: bool = True
) -> Account:
    """Resolve an account by public id within the household. Unlike
    ledger.service.resolve_account, this can return archived accounts (needed
    for update/unarchive)."""
    stmt = select(Account).where(
        Account.public_id == public_id,
        Account.household_id == household_id,
        Account.deleted_at.is_(None),
    )
    if not include_archived:
        stmt = stmt.where(Account.archived_at.is_(None))
    result = await session.execute(stmt)
    account = result.scalar_one_or_none()
    if account is None:
        raise LedgerError("Account not found.")
    return account


async def list_accounts(
    session: AsyncSession, household_id: int, *, include_archived: bool = False
) -> list[Account]:
    stmt = select(Account).where(
        Account.household_id == household_id,
        Account.deleted_at.is_(None),
    )
    if not include_archived:
        stmt = stmt.where(Account.archived_at.is_(None))
    result = await session.execute(stmt.order_by(Account.name))
    return list(result.scalars().all())


async def update_account(
    session: AsyncSession,
    *,
    household_id: int,
    public_id: str,
    name: str | None = None,
    institution_public_id: str | None = None,
    clear_institution: bool = False,
    current_balance_minor: int | None = None,
) -> Account:
    account = await get_account(session, household_id, public_id)
    if name is not None:
        clean = name.strip()
        if not clean:
            raise LedgerError("Account name cannot be empty.")
        account.name = clean
    if clear_institution:
        account.institution_id = None
    elif institution_public_id:
        inst = await resolve_institution(session, household_id, institution_public_id)
        account.institution_id = inst.id
    if current_balance_minor is not None:
        # Only meaningful for balance-only accounts; transactions-mode balances
        # are derived and would be overwritten on the next recompute.
        if account.tracking_mode != "balance_only":
            raise LedgerError(
                "Balance can only be set directly on balance-only accounts."
            )
        account.current_balance_minor = current_balance_minor
    await session.flush()
    return account


async def set_archived(
    session: AsyncSession, *, household_id: int, public_id: str, archived: bool
) -> Account:
    from datetime import UTC, datetime

    account = await get_account(session, household_id, public_id)
    account.archived_at = datetime.now(UTC) if archived else None
    await session.flush()
    return account


async def recompute_account_balance(session: AsyncSession, account: Account) -> None:
    """Refresh the cached balance for a transactions-mode account (sum of live
    transactions). No-op for balance-only accounts, whose balance is user-set.
    T-061 calls this after any transaction insert/edit/delete."""
    if account.tracking_mode != "transactions":
        return
    result = await session.execute(
        select(func.coalesce(func.sum(Transaction.amount_minor), 0)).where(
            Transaction.account_id == account.id,
            Transaction.deleted_at.is_(None),
        )
    )
    account.current_balance_minor = int(result.scalar_one())


def serialize_account(account: Account, *, institution: Institution | None = None) -> dict:
    return {
        "id": account.public_id,
        "name": account.name,
        "type": account.type,
        "tracking_mode": account.tracking_mode,
        "currency": account.currency,
        "current_balance_minor": account.current_balance_minor,
        "archived": account.archived_at is not None,
        "institution": (
            {"id": institution.public_id, "name": institution.name}
            if institution
            else None
        ),
    }


def serialize_institution(inst: Institution) -> dict:
    return {
        "id": inst.public_id,
        "name": inst.name,
        "kind": inst.kind,
    }
