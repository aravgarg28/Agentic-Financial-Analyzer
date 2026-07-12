"""
Agentic Financial Analyzer — FastAPI backend
"""
import os
import time
from collections import defaultdict
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

load_dotenv(dotenv_path="../.env")

from app.config import settings
from app.observability import (
    ObservabilityMiddleware,
    configure_logging,
    install_exception_handlers,
)
from app.routes.analytics import router as analytics_router
from app.routes.auth import router as auth_router
from app.routes.query import router as query_router

# Structured JSON logging with secret redaction (T-004).
configure_logging(secrets=[settings.groq_api_key, settings.secret_key])

# ── Rate Limiter Middleware ────────────────────────────────────────────────────

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory sliding-window rate limiter.
    Limits agent/query to 30 requests per minute per IP.
    """
    def __init__(self, app, max_requests: int = 30, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        # Only rate-limit the agent endpoint (the expensive one)
        if request.url.path == "/agent/query":
            client_ip = request.client.host if request.client else "unknown"
            now = time.time()
            # Prune old entries
            self.requests[client_ip] = [
                t for t in self.requests[client_ip]
                if t > now - self.window_seconds
            ]
            if len(self.requests[client_ip]) >= self.max_requests:
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded. Max 30 requests per minute.",
                )
            self.requests[client_ip].append(now)

        return await call_next(request)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema is owned by Alembic migrations (T-005); the app no longer creates
    # tables on startup. Run `alembic upgrade head` before serving.
    yield


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Agentic Financial Analyzer",
    version="1.0",
    lifespan=lifespan,
)

# CORS — restrict to known frontend origins (never use * with credentials)
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
# In production, add the real frontend domain
_prod_origin = os.getenv("FRONTEND_ORIGIN")
if _prod_origin:
    ALLOWED_ORIGINS.append(_prod_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

# Rate limiter (30 agent queries per minute per IP) — replaced with a shared,
# proper-429 limiter in T-012.
app.add_middleware(RateLimitMiddleware, max_requests=30, window_seconds=60)

# Outermost: request id, security headers, access logging (T-004).
app.add_middleware(ObservabilityMiddleware)

# Sanitized catch-all error responses (no stack traces to clients).
install_exception_handlers(app)

# Register routers
app.include_router(query_router)
app.include_router(analytics_router)
app.include_router(auth_router)


@app.get("/")
def read_root():
    return {"status": "success", "message": "Backend is running and connected to LangChain!"}


@app.get("/health")
async def health():
    return {"status": "healthy"}
