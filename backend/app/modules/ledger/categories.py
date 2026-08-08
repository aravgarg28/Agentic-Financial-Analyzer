"""Category taxonomy service (T-062).

System defaults (household_id NULL, is_system) are shared and read-only; user
categories are household-scoped and support a 2-level hierarchy. Uncategorized is
represented as NULL category_id everywhere (never a magic row) and surfaced
explicitly by callers. Type is one of income/expense/transfer.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ledger.models import Category
from app.modules.ledger.service import LedgerError, resolve_transaction

CATEGORY_TYPES = frozenset({"income", "expense", "transfer"})


async def list_categories(
    session: AsyncSession, household_id: int, *, include_system: bool = True
) -> list[Category]:
    """System defaults + this household's categories, excluding soft-deleted."""
    scope = Category.household_id == household_id
    if include_system:
        scope = scope | Category.household_id.is_(None)
    result = await session.execute(
        select(Category)
        .where(scope, Category.deleted_at.is_(None))
        .order_by(Category.type, Category.name)
    )
    return list(result.scalars().all())


async def _resolve_own_category(
    session: AsyncSession, household_id: int, category_id: int
) -> Category:
    """Resolve a category the household OWNS (system categories are read-only)."""
    result = await session.execute(
        select(Category).where(
            Category.id == category_id,
            Category.household_id == household_id,
            Category.deleted_at.is_(None),
        )
    )
    cat = result.scalar_one_or_none()
    if cat is None:
        raise LedgerError("Category not found.")
    return cat


async def _resolve_parent(
    session: AsyncSession, household_id: int, parent_id: int
) -> Category:
    """A parent must be one of the household's own top-level categories, so the
    tree never exceeds 2 levels (FIN taxonomy rule 6.1)."""
    parent = await _resolve_own_category(session, household_id, parent_id)
    if parent.parent_id is not None:
        raise LedgerError("Categories can be nested at most 2 levels deep.")
    return parent


async def create_category(
    session: AsyncSession,
    *,
    household_id: int,
    name: str,
    type: str,
    parent_id: int | None = None,
) -> Category:
    clean = name.strip()
    if not clean:
        raise LedgerError("Category name is required.")
    if type not in CATEGORY_TYPES:
        raise LedgerError(f"Invalid category type: {type!r}.")
    if parent_id is not None:
        parent = await _resolve_parent(session, household_id, parent_id)
        if parent.type != type:
            raise LedgerError("A subcategory must share its parent's type.")

    cat = Category(
        household_id=household_id,
        parent_id=parent_id,
        name=clean,
        type=type,
        is_system=False,
    )
    session.add(cat)
    try:
        await session.flush()
    except IntegrityError as exc:  # unique (household_id, parent_id, name)
        await session.rollback()
        raise LedgerError("A category with that name already exists here.") from exc
    return cat


async def update_category(
    session: AsyncSession,
    *,
    household_id: int,
    category_id: int,
    name: str | None = None,
    parent_id: int | None = None,
    clear_parent: bool = False,
) -> Category:
    cat = await _resolve_own_category(session, household_id, category_id)
    if name is not None:
        clean = name.strip()
        if not clean:
            raise LedgerError("Category name cannot be empty.")
        cat.name = clean
    if clear_parent:
        cat.parent_id = None
    elif parent_id is not None:
        if parent_id == cat.id:
            raise LedgerError("A category cannot be its own parent.")
        parent = await _resolve_parent(session, household_id, parent_id)
        if parent.type != cat.type:
            raise LedgerError("A subcategory must share its parent's type.")
        cat.parent_id = parent_id
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise LedgerError("A category with that name already exists here.") from exc
    return cat


async def delete_category(
    session: AsyncSession, *, household_id: int, category_id: int
) -> None:
    """Soft-delete a user category and its direct children. Transactions keep
    their category_id pointing at a now-hidden row until recategorized; insights
    already fold unknown/hidden categories into 'Uncategorized'."""
    cat = await _resolve_own_category(session, household_id, category_id)
    now = datetime.now(UTC)
    cat.deleted_at = now
    children = await session.execute(
        select(Category).where(
            Category.parent_id == cat.id, Category.deleted_at.is_(None)
        )
    )
    for child in children.scalars():
        child.deleted_at = now
    await session.flush()


async def recategorize_transaction(
    session: AsyncSession,
    *,
    household_id: int,
    transaction_public_id: str,
    category_id: int | None,
):
    """Set (or clear, when category_id is None) a transaction's category. The
    category must be visible to the household (own or system)."""
    tx = await resolve_transaction(session, household_id, transaction_public_id)
    if category_id is not None:
        result = await session.execute(
            select(Category.id).where(
                Category.id == category_id,
                (Category.household_id == household_id)
                | (Category.household_id.is_(None)),
                Category.deleted_at.is_(None),
            )
        )
        if result.scalar_one_or_none() is None:
            raise LedgerError("Category not found.")
    tx.category_id = category_id
    await session.flush()
    return tx


def serialize_category(cat: Category) -> dict:
    return {
        "id": cat.id,
        "name": cat.name,
        "type": cat.type,
        "parent_id": cat.parent_id,
        "is_system": cat.is_system,
    }
