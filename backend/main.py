"""
Agentic Financial Analyzer — FastAPI backend
"""
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv(dotenv_path="../.env")

from app.config import settings
from app.modules.identity.routes import household_router
from app.modules.identity.routes import router as auth_router
from app.modules.ingestion.routes import router as ingestion_router
from app.modules.insights.agent_routes import router as agent_router
from app.modules.insights.routes import router as insights_router
from app.modules.ledger.routes import router as ledger_router
from app.observability import (
    ObservabilityMiddleware,
    configure_logging,
    install_exception_handlers,
)

# Structured JSON logging with secret redaction (T-004).
configure_logging(secrets=[settings.groq_api_key, settings.secret_key])


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

# CORS — restrict to known frontend origins (never use * with credentials).
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
_prod_origin = os.getenv("FRONTEND_ORIGIN")
if _prod_origin:
    ALLOWED_ORIGINS.append(_prod_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
)

# Rate limiting is now enforced as per-route FastAPI dependencies (T-012,
# app.modules.common.ratelimit), returning proper 429s. The old in-memory
# BaseHTTPMiddleware limiter (which surfaced as 500s — INF-05) was removed.

# Outermost: request id, security headers, access logging (T-004).
app.add_middleware(ObservabilityMiddleware)

# Sanitized catch-all error responses (no stack traces to clients).
install_exception_handlers(app)

# Domain routers (all session-authenticated; no client-supplied identity).
app.include_router(auth_router)
app.include_router(household_router)
app.include_router(insights_router)
app.include_router(ledger_router)
app.include_router(ingestion_router)
app.include_router(agent_router)


@app.get("/")
def read_root():
    return {"status": "success", "message": "Agentic Financial Analyzer API"}


@app.get("/health")
async def health():
    return {"status": "healthy"}
