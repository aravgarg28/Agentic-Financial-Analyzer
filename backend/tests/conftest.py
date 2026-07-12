"""
Shared pytest fixtures.

The harness starts intentionally small (T-002): an ASGI client that exercises
the app without a database. Database-backed fixtures are layered on in later
tasks (T-006+) once the canonical schema and migrations exist.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from main import app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """An HTTP client bound to the ASGI app.

    Uses ASGITransport, which does not run lifespan events, so tests that do not
    need the database (e.g. health checks) run without any external services.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
