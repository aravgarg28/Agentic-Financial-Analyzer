"""categories unique NULLS NOT DISTINCT (T-062)

Revision ID: 563b5843825a
Revises: d2c830d4ff52
Create Date: 2026-08-08

The original uq_categories_scope_name (household_id, parent_id, name) used the
default NULLS DISTINCT, so top-level categories (parent_id NULL) could be
duplicated within a household. Recreate it with NULLS NOT DISTINCT (PG15+) so
NULL parent_id / household_id participate in uniqueness. Requires PostgreSQL 15+.
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "563b5843825a"
down_revision: str | Sequence[str] | None = "d2c830d4ff52"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NAME = "uq_categories_scope_name"


def upgrade() -> None:
    op.drop_constraint(_NAME, "categories", type_="unique")
    op.execute(
        f"ALTER TABLE categories ADD CONSTRAINT {_NAME} "
        "UNIQUE NULLS NOT DISTINCT (household_id, parent_id, name)"
    )


def downgrade() -> None:
    op.drop_constraint(_NAME, "categories", type_="unique")
    op.execute(
        f"ALTER TABLE categories ADD CONSTRAINT {_NAME} "
        "UNIQUE (household_id, parent_id, name)"
    )
