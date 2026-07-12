# Target State Architecture

Status: Proposed (approved plan). Style: **modular monolith + one background worker**. Justification in ADR-01 (`architecture-decisions.md`). Honors D6 (zero-budget) and D8 (free-tier hosting).

## 1. Architectural style

A single deployable FastAPI application organized into internal **modules** with explicit interfaces, plus a single **worker** process that consumes a Postgres-backed job queue. No microservices: there is no deployment-independence or independent-scaling evidence, the team is one person, and free tiers penalize many services (each sleeps/cold-starts separately). See ADR-01.

```
                         ┌───────────────────────────────────────┐
   Browser (Next.js) ───►│  API service (FastAPI, modular)       │
     HttpOnly cookie     │  identity│ledger│ingestion│insights│  │
                         │  agent│ops   (shared domain + db)      │
                         └───────┬───────────────────────┬───────┘
                                 │ enqueue jobs           │ read/write
                    ┌────────────▼──────────┐   ┌─────────▼───────────┐
                    │ jobs table (Postgres) │   │ Postgres (Neon/Supa)│
                    └────────────┬──────────┘   │  canonical ledger   │
                                 │ poll         └─────────┬───────────┘
                    ┌────────────▼──────────┐             │
                    │ Worker (same codebase)│─────────────┘
                    │ imports, recurring,   │      ┌──────────────────┐
                    │ alerts, export/delete,│      │ Redis (Upstash)  │
                    │ aggregator sync       │      │ sessions? cache, │
                    └───────────┬───────────┘      │ chat window, rate│
                                │ minimized prompt └──────────────────┘
                    ┌───────────▼───────────┐
                    │ LLM free tier (Groq)  │  (aggregates + cited rows only)
                    └───────────────────────┘
```

## 2. Modules, responsibilities, interfaces, data ownership

Each module owns its tables; other modules call it through a Python service interface (function calls within the monolith), never by reaching into another module's tables directly. This keeps a clean seam if a module ever must be extracted later.

| Module | Responsibility | Owns (tables) | Key interface (sync) |
|---|---|---|---|
| **identity** | registration, login, sessions, households, memberships, consent, audit | `users, sessions, households, memberships, consent_records, audit_events` | `authenticate(cookie)→Principal{user_id,household_id}`; `create_household_for(user)`; `record_audit(event)` |
| **ledger** | accounts, canonical transactions, merchants, categories, rules, transfers, balances, splits, refunds | `accounts, transactions, merchants, categories, categorization_rules, transfers, balance_snapshots` | `list_transactions(principal, filter)`; `upsert_transaction(...)`; `recategorize(...)`; `reconstruct_balance(account, range)` |
| **ingestion** | import batches, staged records, mapping presets, dedup, commit/rollback, aggregator connections | `import_batches, imported_records, column_mappings, institutions, financial_connections` | `stage_csv(principal, file, mapping)`; `commit_batch(batch)`; `rollback_batch(batch)`; `sync_connection(connection)` |
| **insights** | budgets, recurring series, cash flow, net worth, goals, liabilities, holdings (balance-only), alerts, forecasts, scenarios | `budgets, recurring_series, goals, liabilities, holdings, alerts, forecasts, scenarios` | deterministic calculators: `cash_flow(principal, month)`, `net_worth(principal, asof)`, `detect_recurring(...)`, `forecast(...)`, `run_scenario(...)` |
| **agent** | conversation orchestration, read-only tools (thin wrappers over ledger/insights calculators), proposal objects, citations, memory | `agent_conversations, agent_actions` (+ Redis chat window) | `answer(principal, question)→{narrative, citations, proposals}` |
| **ops** | job queue, backups trigger, export/delete jobs, health, metrics | `jobs` | `enqueue(job)`; worker `run()` loop |

**Data-ownership rule:** cross-module reads go through interfaces; the only shared primitive is the `Principal` (derived from the session) and the `household_id` scoping applied inside every owning module.

## 3. Synchronous flows

- **Authenticated request:** cookie → `identity.authenticate` → `Principal` → route handler calls owning module's interface with the principal → module scopes all queries by `principal.household_id` → response (money converted to major units at this boundary only).
- **Dashboard read:** insights/ledger calculators run deterministic SQL, return typed results.
- **Agent question:** agent module calls read-only calculators, assembles minimized context (aggregates + only the specific rows to be cited), calls the LLM for narration, attaches citations, returns proposals (never executes them).
- **Mutation:** always an explicit authorized endpoint (`POST /transactions/{id}/recategorize`, `POST /budgets`, `POST /proposals/{id}/confirm`) — never inside the agent loop.

## 4. Asynchronous flows (worker)

Enqueued as rows in `jobs` (Postgres) with type, payload, status, attempts, run_after; worker polls with `SELECT ... FOR UPDATE SKIP LOCKED`. Job types:
- `csv_commit` (large batches), `aggregator_sync`, `recurring_detect`, `alert_scan`, `data_export`, `account_delete`, `backup_verify`.
- Idempotent by design (each job re-runnable); failures retried with backoff, then dead-lettered (status=failed) and surfaced as an ops alert.

Why Postgres-backed queue and not Celery/RabbitMQ/SQS: zero extra infra, zero cost, transactional enqueue with the same DB, adequate for beta volume (ADR-05).

## 5. External providers (all free tier — D6/D8)

| Provider | Use | Free-tier note |
|---|---|---|
| Neon **or** Supabase | Postgres (canonical store) | persistent free tier; **Render free Postgres explicitly rejected** (90-day expiry) |
| Upstash | Redis (cache, chat window, rate-limit, optionally session store) | free tier, auth+TLS |
| Groq (default) / Gemini (swap) | LLM narration only | free tier; data-minimized inputs (D7); provider adapter isolates choice |
| Render | API web + worker + frontend | free web services; sleep acceptable for beta |
| GitHub Actions | CI, nightly encrypted backups, scheduled tasks | free minutes |
| Teller (candidate) / SimpleFIN | aggregator (R3, if verified free) | must re-verify free tier at implementation; else feature slips |

**Sessions store decision:** sessions live in Postgres (durable, revocable, survives Redis eviction); Redis holds only ephemeral cache/rate-limit/chat-window. (ADR-02.)

## 6. Deployment topology (free)

- One Render web service (API), one Render **background worker** (same image, `worker` entrypoint), one Render web service (Next.js). Neon/Supabase Postgres, Upstash Redis as managed externals.
- Secrets via Render env vars (never committed). Frontend→API via same-site config; cookies scoped appropriately across the two Render subdomains (documented in security-model).
- Free-tier sleep mitigated by a free uptime pinger for the API and a "warm on demand" acceptance for beta; financial durability rests on managed Postgres + nightly encrypted dumps, not on Render.

## 7. Scaling boundaries (honest, for beta scale D9)

- Target: <100 users, ~10k transactions/user, imports of low-thousands rows. Postgres handles this trivially with proper indexes (see `data-model.md`).
- **First real bottleneck** would be the LLM free-tier rate limit, not the datastore — mitigated by data minimization, caching deterministic results, and per-user rate limits.
- **Extraction seam if ever needed:** the worker is already a separate process; the modular interfaces mean `ingestion` or `agent` could become a service later. No such move is justified now (ADR-01). Partitioning/cursor pagination are designed-in at the query layer but not physically partitioned until volume warrants.

## 8. Cross-cutting concerns

- **Tenant isolation:** enforced in every module's data access by a mandatory `household_id` filter derived from `Principal`; no endpoint or tool accepts a client- or model-supplied tenant. A shared test asserts this across all routes and tools.
- **Money:** integer minor units end to end; conversion only at serialization.
- **Auditing:** identity.record_audit called on auth events, imports, mutations, agent proposals/confirmations, exports, deletions.
- **Observability:** structured logs with request IDs, redaction; `/health` includes DB+Redis checks; job-queue depth exposed.
