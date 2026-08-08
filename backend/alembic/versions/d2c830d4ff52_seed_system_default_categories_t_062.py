"""seed system default categories (T-062)

Revision ID: d2c830d4ff52
Revises: a7ef2f838961
Create Date: 2026-08-08

Inserts the shared system-default category taxonomy (household_id NULL,
is_system=true) available to every household. The canonical list lives in
``app.modules.ledger.system_categories`` (imported here as a plain list of
(name, type) tuples — no ORM dependency). Idempotent via a NOT EXISTS guard so
re-running, or running after a manual seed, is safe. Changing the list later
requires a NEW migration; databases already at this revision won't re-run it.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.modules.ledger.system_categories import SYSTEM_CATEGORIES

# revision identifiers, used by Alembic.
revision: str = "d2c830d4ff52"
down_revision: str | Sequence[str] | None = "a7ef2f838961"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for name, type_ in SYSTEM_CATEGORIES:
        op.execute(
            sa.text(
                """
                INSERT INTO categories (household_id, parent_id, name, type, is_system)
                SELECT NULL, NULL, :name, :type, true
                WHERE NOT EXISTS (
                    SELECT 1 FROM categories
                    WHERE household_id IS NULL AND parent_id IS NULL AND name = :name
                )
                """
            ).bindparams(name=name, type=type_)
        )


def downgrade() -> None:
    # Remove only the system defaults this migration owns. Transactions
    # reference category_id ON DELETE SET NULL, so this won't orphan rows.
    names = [n for n, _ in SYSTEM_CATEGORIES]
    op.execute(
        sa.text(
            "DELETE FROM categories WHERE is_system = true AND household_id IS NULL "
            "AND name = ANY(:names)"
        ).bindparams(names=names)
    )
