"""T-004: security headers, request-id correlation, sanitized errors (APP-01/INF-06)."""
from __future__ import annotations

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.observability import ObservabilityMiddleware, install_exception_handlers


async def test_security_headers_present(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "Strict-Transport-Security" in resp.headers
    assert resp.headers["Content-Security-Policy"] == (
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    )


async def test_request_id_header_present(client: AsyncClient) -> None:
    resp = await client.get("/health")
    rid = resp.headers.get("X-Request-ID")
    assert rid and len(rid) == 32


async def test_unhandled_exception_is_sanitized() -> None:
    # A tiny app whose route raises, wired with the same handler + middleware.
    app = FastAPI()
    app.add_middleware(ObservabilityMiddleware)
    install_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("super secret internal detail")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.get("/boom")

    assert resp.status_code == 500
    body = resp.json()
    assert body["error"] == "Internal server error"
    assert "request_id" in body
    # The internal detail must never reach the client.
    assert "super secret internal detail" not in resp.text
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
