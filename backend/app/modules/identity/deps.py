"""FastAPI dependencies for authentication, tenancy, and CSRF (T-011/T-020).

``require_principal`` is the single gate every data route depends on. It reads
the session cookie, validates it server-side, and returns a Principal whose
``household_id`` scopes all queries. Client-supplied identity is never trusted
(SEC-01). Mutating routes additionally require ``csrf_guard``.
"""
from __future__ import annotations

from fastapi import Depends, Request
from fastapi import status as http_status
from fastapi.exceptions import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.modules.identity.service import Principal, resolve_session

# Origins permitted to make browser requests. Mirrors the CORS allowlist in
# main.py; the CSRF check below is a second, independent gate.
_ALLOWED_ORIGINS = {
    "http://localhost:3000",
    "http://127.0.0.1:3000",
}
_prod_origin = __import__("os").getenv("FRONTEND_ORIGIN")
if _prod_origin:
    _ALLOWED_ORIGINS.add(_prod_origin)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def require_principal(
    request: Request, db: AsyncSession = Depends(get_db)
) -> Principal:
    """Resolve the authenticated Principal or raise 401.

    Uses a generic 401 (never 404/403 distinctions) so the endpoint leaks no
    information about session state. The idle window slide is committed here.
    """
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    principal = await resolve_session(db, raw_token=token)
    if principal is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    # Persist the slid idle-expiry / last_seen update.
    await db.commit()
    return principal


async def csrf_guard(request: Request) -> None:
    """Reject mutating cross-site requests (SEC / security-model §3).

    Requires BOTH an allowlisted Origin (when the header is present) and the
    ``X-Requested-With`` header that browsers will not attach on a simple
    cross-site form/img request. Cheap, dependency-free CSRF defence that pairs
    with SameSite=Lax cookies.
    """
    origin = request.headers.get("origin")
    if origin is not None and origin not in _ALLOWED_ORIGINS:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN, detail="Cross-origin request rejected"
        )
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Missing required X-Requested-With header",
        )
