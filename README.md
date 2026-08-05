# Agentic Financial Analyzer

A personal financial analysis app: a Next.js dashboard plus a LangChain ReAct
agent (Groq Llama 3.3 70B) that answers questions over your own transactions —
spending breakdowns, trends, anomalies, cash flow, and budgets.

> **Status: Release 0 (security & correctness foundation).** The data model,
> authentication, tenancy, and agent isolation have been rebuilt from the
> prototype. Import (CSV/OFX), accounts UI, and evidence-cited AI answers are
> later releases — see `docs/execution/roadmap.md`.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Next.js Frontend (:3000)                  │
│   Dashboard (charts) · Chat (SSE) · cookie-based API client  │
└───────────────────────────────┬─────────────────────────────┘
                        HTTP / SSE (HttpOnly session cookie)
┌───────────────────────────────┴─────────────────────────────┐
│                   FastAPI Backend (:8000)                     │
│   identity · insights · ledger · agent   (modular monolith)   │
│   Session auth · per-household tenancy · Groq ReAct agent      │
│           │                                    │              │
│  ┌────────▼─────────────┐            ┌─────────▼───────────┐  │
│  │ PostgreSQL (:5432)   │            │  Redis (:6379)      │  │
│  │ schema via Alembic   │            │  agent chat memory  │  │
│  │ money = minor units  │            │  (24h TTL)          │  │
│  └──────────────────────┘            └─────────────────────┘  │
└───────────────────────────────────────────────────────────────┘
```

Money is stored as integer **minor units** (cents) + an ISO-4217 currency —
never floats. Every domain row is scoped by `household_id`, resolved from the
server-side session, never from client input.

## Quick Start

### 1. Configure environment
```bash
# In .env
GROQ_API_KEY=gsk_your_actual_key_here
```

### 2. Start the datastores + backend
```bash
docker-compose up -d
```
The backend applies Alembic migrations on startup (schema is migration-owned).

### 3. Seed demo data (optional, non-production only)
```bash
docker compose exec backend python -m scripts.seed_demo
```
This creates one demo household and prints a **randomly generated** password to
log in with. It never drops or truncates data.

### 4. Start the frontend
```bash
cd frontend && npm install && npm run dev
```

### 5. Open the app
Visit **http://localhost:3000**, then register an account (email + a password of
at least 10 characters) or log in with the seeded demo credentials.

## Features

### Dashboard (`/insights/*`)
- Income, expenses, and **net cash flow** for a calendar month (household-local
  month boundaries — not a rolling 30-day window)
- Spending by category, monthly trends, top payees, recent transactions
- Per-category monthly budgets with overspend alerts

### AI Chat Agent (`/agent/query`, SSE)
- **7 read-only tools**: query transactions, spending-by-category, monthly
  trends, anomaly detection, merchant analysis, cash-flow summary, budgets
- The agent has **no mutation tools** and **no identity parameters** — the
  household is injected server-side, so it can only ever read the signed-in
  household's data
- Streams reasoning/tool steps over SSE; conversation memory in Redis (24h TTL)
- Beta: figures may be imprecise until evidence-cited answers ship (R3)

### Auth & security
- argon2id password hashing; opaque server-side sessions in HttpOnly/Secure/
  SameSite cookies; login throttling + account lockout; CSRF protection
- Per-request tenant isolation enforced and covered by a cross-tenant test matrix

### Selected API endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/auth/register`, `/auth/login`, `/auth/logout` | POST | Session auth |
| `/auth/me` | GET | Current profile |
| `/insights/cash-flow-summary` | GET | Income vs. expenses, net cash flow |
| `/insights/spending-by-category` | GET | Category breakdown |
| `/insights/monthly-trends` | GET | Monthly income/spending |
| `/insights/budgets` | GET/PUT | Read / upsert monthly budgets |
| `/ledger/transactions` | POST | Add a manual transaction |
| `/agent/query` | POST | SSE streaming agent query |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js, React 19, Recharts, Framer Motion |
| Backend | FastAPI, SQLAlchemy (async), Alembic, LangChain, Groq (Llama 3.3 70B) |
| Database | PostgreSQL |
| Cache | Redis (agent chat memory, 24h TTL) |
| Infra | Docker Compose (dev); free-tier hosting planned (`docs/`) |

## Testing

```bash
cd backend
poetry run pytest                       # fast unit + DB-backed API tests
RUN_MIGRATION_TESTS=1 poetry run pytest  # also runs Alembic lifecycle tests
```
DB-backed tests self-skip if no `DATABASE_URL` Postgres is reachable.

> **Note:** `benchmark.py` is a prototype latency script that predates the R0
> auth/tool changes and does not currently run against the secured API. A
> deterministic evaluation harness (golden numeric answers + an injection test
> suite) is planned — see `docs/architecture/agent-design.md`.
