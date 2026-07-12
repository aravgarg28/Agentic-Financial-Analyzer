"""
Observability primitives (T-004):

- JSON structured logging with a redaction filter for known secrets.
- A pure-ASGI middleware that assigns a request id, emits security headers,
  and writes one access-log line per request. Pure ASGI (not BaseHTTPMiddleware)
  so it never buffers response bodies and is safe for SSE streaming.
- A global exception handler that returns a sanitized body plus the request id.

Nothing here leaks stack traces or secrets to clients; full detail goes to the
server logs, correlated by request id.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

# Paths that serve HTML/JS (Swagger, ReDoc) and must not get a locked-down CSP.
_DOCS_PREFIXES = ("/docs", "/redoc", "/openapi.json")

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
}
_API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"


class _RedactionFilter(logging.Filter):
    """Replace known secret substrings in log output with '***'."""

    def __init__(self, secrets: list[str]) -> None:
        super().__init__()
        # Only redact substantial secrets to avoid mangling ordinary text.
        self._secrets = [s for s in secrets if s and len(s) >= 6]

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        redacted = msg
        for secret in self._secrets:
            if secret in redacted:
                redacted = redacted.replace(secret, "***")
        if redacted != msg:
            record.msg = redacted
            record.args = ()
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(secrets: list[str] | None = None, level: int = logging.INFO) -> None:
    """Install the JSON formatter and redaction filter on the root logger."""
    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter())
    handler.addFilter(_RedactionFilter(secrets or []))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


access_logger = logging.getLogger("app.access")


class ObservabilityMiddleware:
    """Pure-ASGI middleware: request id, security headers, access logging, and
    a sanitized 500 for unhandled exceptions.

    Handling the exception here (rather than relying on Starlette's outer
    ServerErrorMiddleware) means the sanitized error response still carries the
    security headers and the correlating request id.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    def _decorate(self, message: Message, path: str, rid: str) -> None:
        headers = MutableHeaders(scope=message)
        headers["X-Request-ID"] = rid
        for key, value in _SECURITY_HEADERS.items():
            headers[key] = value
        if not path.startswith(_DOCS_PREFIXES):
            headers["Content-Security-Policy"] = _API_CSP

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        rid = uuid.uuid4().hex
        token = request_id_var.set(rid)
        start = time.perf_counter()
        path = scope.get("path", "")
        method = scope.get("method", "")
        status_holder = {"code": 0}
        started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                status_holder["code"] = message["status"]
                self._decorate(message, path, rid)
            await send(message)

        try:
            try:
                await self.app(scope, receive, send_wrapper)
            except Exception:
                logging.getLogger("app.error").exception("Unhandled exception")
                if started:
                    # Response already began streaming; cannot replace it.
                    raise
                status_holder["code"] = 500
                response = JSONResponse(
                    status_code=500,
                    content={"error": "Internal server error", "request_id": rid},
                )
                response.raw_headers.append((b"x-request-id", rid.encode()))
                for key, value in _SECURITY_HEADERS.items():
                    response.raw_headers.append((key.encode(), value.encode()))
                if not path.startswith(_DOCS_PREFIXES):
                    response.raw_headers.append(
                        (b"content-security-policy", _API_CSP.encode())
                    )
                await response(scope, receive, send)
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 1)
            access_logger.info(
                "%s %s -> %s (%sms)", method, path, status_holder["code"], duration_ms
            )
            request_id_var.reset(token)


def install_exception_handlers(app: object) -> None:
    """Register a catch-all handler that never leaks internals to the client."""
    logger = logging.getLogger("app.error")

    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception")
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "request_id": request_id_var.get()},
        )

    # FastAPI/Starlette expose add_exception_handler with the same signature.
    handler: Callable[[Request, Exception], Awaitable[JSONResponse]] = _unhandled
    app.add_exception_handler(Exception, handler)  # type: ignore[attr-defined]
