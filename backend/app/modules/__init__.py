"""
Domain modules for the modular monolith (target-state.md §2).

Importing this package imports every module's ORM models so their tables are
registered on the shared ``Base.metadata`` — used by Alembic autogenerate and
by the application at runtime.
"""
from __future__ import annotations

from app.modules.identity import models as identity_models  # noqa: F401
from app.modules.ingestion import models as ingestion_models  # noqa: F401
from app.modules.insights import models as insights_models  # noqa: F401
from app.modules.ledger import models as ledger_models  # noqa: F401
from app.modules.ops import models as ops_models  # noqa: F401
