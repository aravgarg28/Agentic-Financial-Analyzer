"""Shared pytest fixtures.

Two tiers:
- ``client``: a DB-free ASGI client for smoke/unit tests (T-002).
- ``api`` + ``seed_session``: database-backed fixtures (T-010+). These require a
  reachable Postgres; they self-skip when ``DATABASE_URL`` is unset or the
  server cannot be reached, so a plain ``pytest`` run stays green offline. CI
  provisions Postgres and sets ``DATABASE_URL``.

DB tests use a dedicated ``NullPool`` engine (no connection is cached across
per-test event loops — avoiding asyncpg's cross-loop reuse errors) and override
the app's ``get_db`` dependency to use it. The DB-backed client preloads the
CSRF headers mutating routes require and keeps a cookie jar for session auth.
"""
from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from main import app

CSRF_HEADERS = {
    "Origin": "http://localhost:3000",
    "X-Requested-With": "XMLHttpRequest",
}


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Each test starts with an empty rate-limit window store, so per-IP limits
    don't accumulate across the suite (all tests share one client IP)."""
    from app.modules.common import ratelimit

    ratelimit.store.reset()
    yield
    ratelimit.store.reset()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """An HTTP client bound to the ASGI app, no database required."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


# ── Database-backed fixtures ─────────────────────────────────────────────────

def _database_url() -> str | None:
    url = os.getenv("DATABASE_URL")
    if not url or "@db:" in url:  # default compose host is unreachable in tests
        return None
    return url


# One NullPool engine + sessionmaker for the whole test session. NullPool means
# every checkout opens a fresh connection on the *current* running loop and
# closes it immediately, so nothing is shared across per-test loops.
_TEST_ENGINE = None
_TEST_SESSIONMAKER = None
_SCHEMA_READY = False


def _get_test_sessionmaker():
    global _TEST_ENGINE, _TEST_SESSIONMAKER
    if _TEST_SESSIONMAKER is None:
        url = _database_url()
        _TEST_ENGINE = create_async_engine(url, poolclass=NullPool)
        _TEST_SESSIONMAKER = async_sessionmaker(_TEST_ENGINE, expire_on_commit=False)
    return _TEST_SESSIONMAKER


async def _ensure_schema() -> bool:
    """Create the schema once. Returns False if no DB is reachable."""
    global _SCHEMA_READY
    url = _database_url()
    if url is None:
        return False
    sm = _get_test_sessionmaker()
    if _SCHEMA_READY:
        return True
    import app.modules  # noqa: F401  (register all tables on Base.metadata)
    from app.database import Base

    try:
        async with _TEST_ENGINE.begin() as conn:
            await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS citext")
            await conn.run_sync(Base.metadata.create_all)
    except Exception:
        return False
    _SCHEMA_READY = True
    _ = sm
    return True


@pytest.fixture
async def seed_session(request) -> AsyncIterator:
    """A raw AsyncSession for arranging test data, with tables truncated first.

    Also overrides the app's ``get_db`` so request handlers use the NullPool
    test engine and see the same database.
    """
    if not await _ensure_schema():
        pytest.skip("DATABASE_URL not set to a reachable Postgres; skipping DB tests")

    from app.database import Base, get_db

    sm = _get_test_sessionmaker()

    table_names = ", ".join(
        f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables)
    )
    async with _TEST_ENGINE.begin() as conn:
        await conn.exec_driver_sql(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE")

    async def _override_get_db():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        async with sm() as session:
            yield session
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
async def api(seed_session) -> AsyncIterator[AsyncClient]:
    """DB-backed ASGI client with CSRF headers and a cookie jar preloaded."""
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver", headers=CSRF_HEADERS
    ) as ac:
        yield ac
