# Implementation Tasks

Status: Proposed backlog. R0 and R1 tasks are fully specified for independent execution by a coding model; R2–R4 are listed at epic granularity with representative tasks (they get full specs when their release starts, informed by what shipped).

## Global conventions (apply to every task; tasks reference these instead of repeating)

- **G-STACK:** Backend `backend/` FastAPI + SQLAlchemy async + Alembic; frontend `frontend/` Next.js 16. New modules per `docs/architecture/target-state.md` §2 layout: `backend/app/modules/{identity,ledger,ingestion,insights,agent,ops}/`.
- **G-MONEY:** all amounts `*_minor BIGINT` + `currency CHAR(3)`; no float in domain code (`docs/architecture/data-model.md`).
- **G-TENANT:** all data access requires `Principal` (session-derived); no client/model-supplied tenant ids anywhere (security-model §4).
- **G-SEC:** no secrets in code/logs; inputs validated with Pydantic; parameterized SQL only; errors sanitized.
- **G-PRIV:** no PII/financial payloads in logs; audit events per security-model §8.
- **G-TESTS:** pytest + pytest-asyncio against a disposable Postgres (docker or Neon branch); every task ships its tests in the same PR; regression tests named after finding IDs where applicable.
- **G-VERIFY:** `cd backend && poetry run pytest`, `poetry run ruff check`, `poetry run mypy app` (once T-003 lands, CI runs these); frontend: `cd frontend && npm run lint && npm run build`.
- **G-DOD (definition of done):** scope implemented; exclusions untouched; tests green locally + CI; migration up+down tested; docs updated where named; PR description maps changes to finding/decision IDs; no new dependencies without free-tier check (ADR-12).
- **G-MODEL:** "Sonnet-class" = current mid-tier coding model is sufficient; "review" flags whether a Fable/architect review is required before merge.

---

# Release 0

## T-001 — Pin backend dependencies and commit lockfile
- **Objective:** reproducible builds (INF-04).
- **Context:** `backend/pyproject.toml` uses `"*"` for every dep; no `poetry.lock` committed.
- **Prerequisites:** none. **Scope:** pin sensible current versions (fastapi, uvicorn, sqlalchemy, asyncpg, alembic, redis, langchain-groq, pydantic v2, pydantic-settings, python-dotenv, httpx, psycopg2-binary → keep only if needed by alembic, else drop); add dev group (pytest, pytest-asyncio, ruff, mypy, argon2-cffi later tasks); `poetry lock`; commit lockfile; remove `pgvector` dep (ADR-07). **Exclusions:** no code changes beyond imports that break from removals.
- **Files:** `backend/pyproject.toml`, `backend/poetry.lock`, `backend/Dockerfile` (build still works). **Data/API/Frontend changes:** none.
- **Security/Privacy:** supply-chain baseline (G-SEC). **Edge cases:** langchain pin conflicts — prefer minimal set that keeps current agent running.
- **Acceptance:** `poetry install` from lockfile succeeds in clean container; app boots; `docker compose build backend` passes.
- **Tests:** none new (build verification). **Verification:** `poetry lock --check`, compose build. **Migration/Rollback:** n/a / revert commit. **Docs:** README dependency section.
- **Risk:** Low. **Model:** Sonnet-class. **Review:** no.

## T-002 — Test harness
- **Objective:** make tests possible (INF-04).
- **Context:** zero tests exist. **Prerequisites:** T-001.
- **Scope:** pytest + pytest-asyncio config; test DB fixture (dockerized Postgres or `DATABASE_URL_TEST`); httpx `AsyncClient` app fixture; factory helpers for users/households (will grow); one smoke test (`GET /health`). **Exclusions:** no CI yet, no feature tests.
- **Files:** `backend/tests/conftest.py`, `backend/tests/test_smoke.py`, pyproject dev deps.
- **Acceptance:** `poetry run pytest` green locally with a fresh DB. **Tests:** the harness itself. **Verification:** G-VERIFY. **Risk:** Low. **Model:** Sonnet-class. **Review:** no.

## T-003 — CI pipeline (GitHub Actions, free)
- **Objective:** every merge gated (INF-04, ADR-12).
- **Context:** no CI exists. **Prerequisites:** T-001, T-002.
- **Scope:** workflow: backend lint (ruff) + type (mypy, permissive start) + pytest w/ Postgres service container; frontend `npm ci && npm run lint && npm run build`; `pip-audit`, `npm audit --audit-level=high` (non-blocking warn initially), `gitleaks` (blocking); alembic drift check added by T-005. **Exclusions:** no deploy automation.
- **Files:** `.github/workflows/ci.yml`, badge in README.
- **Acceptance:** CI green on main; a seeded-secret test branch fails gitleaks. **Verification:** push a PR, observe. **Risk:** Low. **Model:** Sonnet-class. **Review:** no.

## T-004 — Structured logging, sanitized errors, security headers
- **Objective:** INF-06/APP-01 remediation.
- **Context:** raw `str(e)` streamed to clients (`react_agent.py:127`); no headers; print-style logs.
- **Prerequisites:** T-002. **Scope:** JSON logging w/ request-id middleware; global exception handler → `{error, request_id}` only; security-headers middleware (HSTS, nosniff, frame-deny, referrer-policy); agent SSE error event uses same sanitizer; redaction filter for known secret env values. **Exclusions:** audit_events (T-006), rate limiting (T-012).
- **Files:** `backend/app/middleware.py` (new), `main.py`, `react_agent.py` error path, tests.
- **Acceptance/Tests:** error responses contain no exception internals (test with forced failure); headers present on all responses; logs parse as JSON. **Verification:** G-VERIFY. **Risk:** Low. **Model:** Sonnet-class. **Review:** no.

## T-005 — Adopt Alembic
- **Objective:** migrations-only schema lifecycle (INF-01).
- **Context:** `create_all` on startup; alembic dep unconfigured.
- **Prerequisites:** T-002. **Scope:** `alembic init` (async template); baseline migration capturing the CURRENT 3-table schema (so existing dev DBs adopt cleanly per `migration-plan.md` §1); remove `create_all` from lifespan; CI step `alembic upgrade head` + drift check (`alembic check` or autogen-diff-empty assertion). **Exclusions:** no new tables (T-006).
- **Files:** `backend/alembic/**`, `backend/alembic.ini`, `main.py`, CI workflow.
- **Acceptance:** fresh DB reaches current schema via `alembic upgrade head` only; app boots without create_all; downgrade to base works. **Tests:** migration up/down in CI. **Risk:** Medium (schema lifecycle change). **Model:** Sonnet-class. **Review:** yes (migration correctness).

## T-006 — Core target schema, phase 1
- **Objective:** create the R0 slice of `data-model.md`: `households, memberships, sessions, audit_events, jobs`; rebuild `users` (email/citext, argon2 fields, status/lockout); new `accounts, categories, transactions, budgets` per spec with minor-unit money.
- **Context:** prototype tables are unusable for real data (FIN-01/02/08). Per `migration-plan.md`, prototype data is treated as disposable dev data — no production backfill exists yet (there is no production).
- **Prerequisites:** T-005. **Scope:** one Alembic migration creating the new schema (old `transactions/budgets/users` dropped after the dev-data note in migration-plan §2); SQLAlchemy models in module folders; CITEXT extension; FKs/uniques/indexes exactly per data-model.md; `audit_events` writer helper; `jobs` table only (worker comes later). **Exclusions:** endpoints (later tasks), aggregator tables (`institutions, financial_connections` etc. arrive in R1/R2 tasks), balance_snapshots/transfers/etc. (R2).
- **Files:** `backend/app/modules/*/models.py`, migration, `app/models.py` removed/redirected.
- **Data changes:** destructive for dev seed data only (explicitly sanctioned, migration-plan §2). **API changes:** none yet (endpoints break in T-021 rewrite; sequence within one release).
- **Security/Privacy:** G-TENANT columns everywhere; audit helper per §8. **Edge cases:** citext availability on Neon/Supabase (enable extension in migration).
- **Acceptance:** upgrade/downgrade clean; models import; constraint spot-tests (duplicate budget rejected — FIN-08 regression test; float write to amount fails type check).
- **Tests:** constraint tests, audit writer test. **Verification:** G-VERIFY + `alembic upgrade head && alembic downgrade -1`. **Risk:** High (foundation). **Model:** Sonnet-class. **Review:** **yes — Fable review required** (schema is load-bearing).

## T-007 — Non-destructive demo seed
- **Objective:** replace table-dropping seed (INF-01, SEC-06).
- **Context:** `seed.py` drops all tables and creates `player1/password`.
- **Prerequisites:** T-006. **Scope:** new `scripts/seed_demo.py`: creates a clearly-marked demo household + demo user with a RANDOM printed password, realistic transactions/categories/budgets via the normal model layer; refuses to run if `ENVIRONMENT=production`; never drops/truncates. Delete old seed. Remove prefilled credentials from `page.tsx` login form. **Exclusions:** onboarding demo mode UX (T-080).
- **Acceptance:** running twice adds nothing (idempotent by demo-household marker); refuses in production env; login form ships empty (SEC-06 regression test: grep + UI test).
- **Risk:** Low. **Model:** Sonnet-class. **Review:** no.

## T-010 — Password hashing + register/login rebuild
- **Objective:** SEC-03/04(enumeration)/05(policy) remediation.
- **Context:** `auth.py` uses unsalted SHA-256; register leaks existence.
- **Prerequisites:** T-006. **Scope:** argon2-cffi (argon2id) hash/verify; email-based registration (CITEXT unique) with min-10-char + common-password-list check; uniform responses ("if this email is available you'll be able to log in" pattern or identical 200s); login verifies argon2id; `failed_login_count`/`locked_until` fields maintained (throttle logic in T-012); audit events for register/login/failed-login. NO legacy hash migration — old users table was dropped in T-006 (dev data).
- **Exclusions:** sessions (T-011), reset flow (documented manual op procedure in security-model §1 — add `docs/ops/password-reset.md` runbook).
- **Files:** `modules/identity/{service,routes,schemas}.py`, tests, runbook doc.
- **Acceptance:** hashes are argon2id format; wrong password and unknown email produce byte-identical responses + timing-safe verify; weak password rejected. **Tests:** SEC-03/SEC-04 named regressions. **Risk:** Medium. **Model:** Sonnet-class. **Review:** yes.

## T-011 — Server-side sessions + cookie auth + logout
- **Objective:** SEC-02 remediation per ADR-02.
- **Prerequisites:** T-010. **Scope:** on login: 256-bit token, store SHA-256 hash in `sessions` with idle(14d)/absolute(30d) expiries; cookie HttpOnly/Secure/SameSite=Lax, domain/config documented for Render cross-subdomain; `authenticate` dependency → `Principal{user_id, household_id}` (404 on invalid); sliding idle refresh; `/auth/logout` (revoke), `/auth/logout-all`; CSRF: Origin allowlist check + `X-Requested-With` requirement on mutating routes (security-model §3); session purge job handler registered (runs when worker exists). Frontend: `credentials:'include'` in `api.ts`, login stores nothing in JS state beyond profile display, logout button.
- **Exclusions:** endpoint tenancy rewrite (T-021). **Files:** identity module, `frontend/src/lib/api.ts`, `page.tsx` auth wiring, tests.
- **Acceptance:** login sets cookie; API rejects missing/expired/revoked sessions; logout immediate; token never stored server-side in plain; cross-origin POST without proper Origin rejected (CSRF test). **Tests:** SEC-02 named regressions; fixation test (pre-login cookie unused). **Risk:** High (auth core). **Model:** Sonnet-class. **Review:** **yes — Fable review required.**

## T-012 — Rate limiting done right
- **Objective:** SEC-04, INF-05.
- **Context:** current limiter is in-memory middleware raising HTTPException (likely 500) and covers only `/agent/query`.
- **Prerequisites:** T-011. **Scope (revised — security-model §9):** limiter as FastAPI dependency; **in-process bounded-LRU windows** for IP/user scopes (single Render instance; swappable store interface for the future), **Postgres-backed login lockout** (`failed_login_count/locked_until`); scopes: login 5/15min/account + 20/hr/IP, register 5/hr/IP, agent 30/min/user, general 300/min/IP; returns 429 with Retry-After; remove old middleware. Verify INF-05 suspicion (test asserts 429 not 500). No Upstash commands spent on rate limiting (free-quota budget, ADR-12).
- **Acceptance/Tests:** 429 status verified; lockout after 5 failed logins survives an app restart (DB-backed); LRU bounded (memory test); limiter interface swappable. **Risk:** Medium. **Model:** Sonnet-class. **Review:** no.

## T-020 — Principal dependency + household bootstrap
- **Objective:** tenancy foundation (D2, SEC-01 groundwork).
- **Prerequisites:** T-011. **Scope:** registration creates household + owner membership atomically; `Principal` carries household_id; helper `require_principal` used by all subsequent routes; household timezone/base-currency defaults (America/New_York, USD) with settings endpoint (`PATCH /household` tz/currency only).
- **Acceptance:** every new user has exactly one household w/ owner membership; principal resolves both ids in one query. **Tests:** bootstrap atomicity (failure rolls back both). **Risk:** Medium. **Model:** Sonnet-class. **Review:** yes.

## T-021 — Endpoint tenancy rewrite (remove client-supplied identity)
- **Objective:** SEC-01/AGT-05 remediation — THE critical fix.
- **Context:** every analytics/agent route takes `user_id` query/body param.
- **Prerequisites:** T-020, T-006. **Scope:** rewrite all data endpoints onto new schema + Principal: analytics reads (rebuilt as `modules/insights/routes.py` with correct calendar-month/tz logic — fixes FIN-03/04 in the same rewrite since queries are rewritten anyway), budgets CRUD (upsert w/ unique constraint, rowcount-checked — FIN-08), manual transaction add (account-scoped, minor units), agent query endpoint (principal-bound; session_id validated as belonging to the household — AGT-05: Redis key becomes `chat:{household_id}:{conversation}` derived server-side). Remove `user_id` from every schema, route, and `api.ts` call. Frontend updated accordingly.
- **Exclusions:** agent internals (T-030), new ledger features (R1).
- **Files:** `modules/insights/*`, `modules/ledger/*` (minimal), `routes/analytics.py` deleted, `query.py` rewritten, `schemas.py`, `api.ts`, dashboard components.
- **Acceptance:** grep proves no route/schema accepts `user_id`/`household_id` from client; all dashboard features work through cookie auth; month boundaries correct in household tz (FIN-03/04 golden tests).
- **Tests:** SEC-01 regression (fabricated ids ignored), FIN-03/04 goldens. **Risk:** High (touches everything). **Model:** Sonnet-class. **Review:** **yes — Fable review required.**

## T-022 — Cross-tenant test matrix
- **Objective:** prove isolation, permanently (SEC-01 verification).
- **Prerequisites:** T-021. **Scope:** parametrized test: two seeded households; for EVERY registered route (introspected from FastAPI app, allowlist for public routes), request household B's resources with A's session → expect 404/empty, never data; test fails if a new route isn't classified (forces future routes into the matrix). Add Redis-key isolation test (AGT-05).
- **Acceptance:** matrix green; adding an unclassified route breaks CI. **Risk:** Medium (test infra). **Model:** Sonnet-class. **Review:** yes (the matrix design is the guarantee).

## T-030 — Agent stopgap hardening
- **Objective:** AGT-01/02/06 interim remediation (full rebuild is R3).
- **Context:** LLM controls `user_id`; `update_budget` writes; unbounded result contexts.
- **Prerequisites:** T-021. **Scope:** remove `update_budget` + `get_budgets` write path from tools; strip ALL model-supplied identity args — tools receive household_id via closure/context injected at executor level, tool schemas expose no tenant params (regenerate tool signatures); cap tool result rows (≤50) and total context chars; keep answers labeled "beta — numbers may be imprecise" until R3 citations; sanitized error events (from T-004).
- **Acceptance:** prompt "call tools for user_2 / set my budget to 0" cannot mutate anything nor read foreign rows (AGT-01/02 named tests with a stub LLM injecting hostile tool calls); tool schemas contain no user/household params.
- **Risk:** Medium. **Model:** Sonnet-class. **Review:** yes.

## T-040 — Free-tier infrastructure migration
- **Objective:** INF-02/03/08, D8.
- **Scope:** provision Neon (or Supabase) Postgres + Upstash Redis (TLS URLs into Render env); render.yaml: drop Render Postgres block, backend/worker services, frontend build-arg for `NEXT_PUBLIC_API_URL` (build-time, correct public URL — INF-08) or switch frontend to a runtime server-config endpoint; docker-compose split `compose.dev.yml` (reload, local pg/redis, published ports OK for dev) vs prod parity notes; strong local creds still not `user/password`; document the whole topology in `docs/ops/deploy.md`.
- **Prerequisites:** T-003 (CI first so the move is verified). **Acceptance:** staging deploy on free stack serves the app end-to-end; no datastore ports public; browser reaches API at correct URL from deployed frontend. **Risk:** Medium. **Model:** Sonnet-class + human clicks for provisioning (operator involvement flagged). **Review:** no.

## T-041 — Encrypted backups + restore drill
- **Objective:** INF-10.
- **Prerequisites:** T-040. **Scope:** GitHub Actions nightly: `pg_dump` → zstd → `age`-encrypt (key in Actions secret) → upload as artifact w/ 14-day retention; `docs/ops/restore.md` step-by-step; perform one full restore drill into a scratch branch/db and record the log in `docs/ops/restore-drills.md`.
- **Acceptance:** artifact exists nightly; documented drill completed once with verification queries (row counts match). **Risk:** Medium. **Model:** Sonnet-class + operator. **Review:** yes (backup correctness is existential).

## T-050 — Truthful naming & docs sweep
- **Objective:** FIN-07, INF-07, ADR-07.
- **Prerequisites:** T-021 (endpoints already renamed in rewrite — this task verifies + docs). **Scope:** ensure cash-flow naming end-to-end (endpoint, tool name, UI labels); README rewritten to actual architecture (no pgvector, correct tool count, honest benchmark description or benchmark removal note); compose image `ankane/pgvector` → `postgres:16-alpine`.
- **Acceptance:** `grep -ri "net.worth" backend frontend` returns only true net-worth (R2) stubs or nothing; README claims match code. **Risk:** Low. **Model:** Sonnet-class. **Review:** no.

**R0 exit gate G1:** T-001…T-050 done + drill performed → real data allowed.

---

# Release 1

## T-060 — Accounts & institutions CRUD
- **Objective:** feature 4.1 (D10 types).
- **Prerequisites:** G1. **Scope:** institutions + accounts endpoints (create/list/update/archive; type enum incl. balance_only tracking_mode), UI account management screen, current-balance cache field maintained (recompute hook stub); audit events on create/archive.
- **Acceptance:** account lifecycle e2e test; archived accounts hidden from defaults, history intact; cross-tenant matrix auto-covers new routes. **Risk:** Low. **Model:** Sonnet-class. **Review:** no.

## T-061 — Canonical ledger endpoints (manual add/edit/list)
- **Objective:** feature 5.1/5.2 core.
- **Prerequisites:** T-060. **Scope:** transactions list w/ filters+cursor pagination; manual create (account-scoped, minor units, booked_date, category optional); edit (amount/date/category/description) writing audit events; soft delete; merchant auto-create-by-normalized-name; `source='manual'`, fingerprint computed.
- **Acceptance:** property tests: fingerprint stability, minor-unit round-trip; edit audit trail visible; pagination stable under inserts. **Risk:** Medium. **Model:** Sonnet-class. **Review:** yes (ledger semantics).

## T-062 — Category taxonomy
- **Objective:** feature 6.1. **Prerequisites:** T-006 (table exists). **Scope:** system defaults fixture (typed income/expense/transfer), user category CRUD (2-level), uncategorized as NULL surfaced explicitly in UI + filters; recategorize endpoint (used later by proposals).
- **Acceptance:** type-safety tests (income category on expense aggregates per FIN-06 rules defined in insights); uniqueness constraints. **Risk:** Low. **Model:** Sonnet-class. **Review:** no.

## T-063 — Dashboard rebuild on canonical ledger
- **Objective:** replace prototype charts with correct calculators.
- **Prerequisites:** T-061/T-062. **Scope:** insights calculators (spending by category, monthly series by CALENDAR month in household tz, cash flow labeled as such, top merchants, recent transactions) shared by API + future agent tools; frontend charts rewired; month picker uses real months.
- **Acceptance:** golden tests vs hand-computed fixture values (cent-exact); FIN-04 regression (calendar months). **Risk:** Medium. **Model:** Sonnet-class. **Review:** no.

## T-070 — Upload endpoint + documents
- **Objective:** ingestion entry (3.1 upload, file security §10).
- **Prerequisites:** T-060. **Scope:** `POST /imports/upload` (CSV only): size cap 5MB, MIME/extension allowlist, checksum, store bytea in `documents` (+ per-household quota check), create `import_batch(status=staged)` shell + `institutions`/`column_mappings`/`import_batches`/`imported_records` tables migration (R1 slice of data-model).
- **Acceptance:** oversize/wrong-type rejected (tests); duplicate checksum → "already imported" response (FIN-05 groundwork); quota enforced. **Risk:** Medium. **Model:** Sonnet-class. **Review:** yes (first file-handling surface).

## T-071 — Column mapping + saved presets
- **Objective:** 3.1 mapping. **Prerequisites:** T-070. **Scope:** parse endpoint (sniff delimiter/encoding/header → sample rows); mapping schema (date col+format, amount col(s)+sign convention incl. debit/credit pair + parentheses/DR-CR, description, optional category/balance); save/load `column_mappings` per institution; built-in preset data file for ~6 common US bank formats; mapping UI (upload → map → preview).
- **Acceptance:** each preset parses its fixture; saved mapping round-trips; ambiguous columns flagged not guessed. **Risk:** Medium. **Model:** Sonnet-class. **Review:** no.

## T-072 — Staging + row validation
- **Objective:** 3.1 validation (§2.3). **Prerequisites:** T-071. **Scope:** apply mapping → `imported_records` rows (raw JSONB + parsed_{amount_minor,date,currency} + validation JSONB); amount parsing straight-to-minor-units (never float — G-MONEY) w/ thousands separators, negative conventions; date parsing in household tz; per-row error/warning states; batch summary counts.
- **Acceptance:** pathological fixtures (bad dates, currency symbols, thousands separators, BOM, latin-1) parse or flag correctly; NO float appears in parse path (test asserts Decimal/int only). **Risk:** High (correctness core). **Model:** Sonnet-class. **Review:** **yes — Fable review required.**

## T-073 — Duplicate detection engine
- **Objective:** FIN-05 remediation (§2.4). **Prerequisites:** T-072. **Scope:** normalized-description function; fingerprint hash; verdicts vs committed ledger AND intra-batch (new/duplicate/near_dup); external_id path prepared (unused for CSV); verdict stored per record.
- **Acceptance:** re-import same file → 100% duplicate verdicts; overlapping-months file → only overlap flagged; legit same-day-same-amount pair → near_dup (not auto-dropped); property test: fingerprint invariant to whitespace/case. **Risk:** High. **Model:** Sonnet-class. **Review:** **yes — Fable review required.**

## T-074 — Review UX + commit
- **Objective:** §2.5 + commit. **Prerequisites:** T-073. **Scope:** staging review API (paged records w/ decisions accept/skip/merge, bulk ops, editable category) + review UI; commit endpoint: **synchronous transactional chunked insert** of accepted rows → transactions with full provenance, batch → committed; audit event. *(Revised in adversarial review: no worker in R1 — a 5MB CSV commits in seconds synchronously; the worker process ships in R2 where recurring/alerts/export/delete genuinely need it. The `jobs` table from T-006 stays dormant until then.)*
- **Acceptance:** commit atomic (kill mid-commit test leaves batch staged); provenance ids set on every row; committed totals match accepted staging totals (cent-exact test); a 10k-row fixture commits within request timeout on the free tier.
- **Risk:** High. **Model:** Sonnet-class. **Review:** **yes — Fable review required.**

## T-075 — Batch rollback
- **Objective:** §2.6, safety valve. **Prerequisites:** T-074. **Scope:** rollback endpoint: allowed only if batch rows unedited/unlinked (explain refusal reasons); deletes batch's transactions, batch → rolled_back; audited.
- **Acceptance:** import→rollback returns ledger to byte-identical state (checksum over ledger rows); refusal paths tested. **Risk:** Medium. **Model:** Sonnet-class. **Review:** yes.

## T-076 — Import fixture corpus in CI
- **Objective:** lock ingestion correctness. **Prerequisites:** T-074. **Scope:** ≥6 anonymized real-world-shaped bank CSV fixtures (Chase/BoA/Amex/Discover/CapOne/credit-union styles) + expected canonical outputs; end-to-end import tests (upload→map via preset→stage→dedup→commit→assert exact ledger rows); wire into CI.
- **Acceptance:** all fixtures cent-exact; corpus documented for future additions. **Risk:** Low. **Model:** Sonnet-class. **Review:** no.

## T-080 — Onboarding + demo mode
- **Objective:** 1.4/21.7. **Prerequisites:** T-074. **Scope:** first-run checklist UI (create account → import → review → dashboard), empty states, demo-mode button (seeds demo household via T-007 path, clearly labeled, wipeable), disabled in production for real households.
- **Acceptance:** new user reaches populated dashboard unaided (e2e browser test); demo data clearly marked. **Risk:** Low. **Model:** Sonnet-class. **Review:** no.

---

# Release 2–4 (epic granularity; full specs authored at release start)

Representative fully-shaped examples (pattern for the rest):

## T-200 — Transfer detection (E2.2, representative)
- **Objective:** FIN-06 — stop transfer double-counting. **Scope:** candidate matcher (opposite amounts, ±3 days, different accounts, both non-transfer-categorized) as worker job + on-commit hook; candidates UI (confirm/reject); confirmed pairs excluded by cash-flow calculators; `transfers` table migration. **Acceptance:** golden dataset w/ transfers yields correct income/spend; unconfirmed candidates visibly flagged; property test: confirming never changes ledger amounts, only aggregation. **Risk:** High (correctness). **Review:** Fable required.

## T-300 — Agent core rebuild (E3.1, representative)
- **Objective:** agent-design §2–3/7. **Scope:** provider adapter (Groq default w/ Gemini swap); orchestration with budgets (6 tool calls/8k tokens/30s); read-only tools wrapping insights calculators w/ server-injected tenancy; structured profile; Redis window keyed server-side. **Acceptance:** AGT-01 structural test (tool schemas have no tenant params); budget-exhaustion returns labeled partial. **Risk:** High. **Review:** Fable required.

## T-310 — Citations + server-side claim verification (E3.2, representative)
- **Objective:** agent-design §4 (AGT-04). **Scope:** answer schema; validator matching every numeric token to a tool-sourced value (else strip+flag); citation chips UI resolving to rows. **Acceptance:** numeric-agreement eval ≥95%, citation resolvability 100% on fixture suite; fabricated-number fixture blocked. **Risk:** High. **Review:** Fable required.

Remaining epics (E2.1 balances, E2.3 rules, E2.4 recurring, E2.5 budgets/cash-flow/goals/reports, E2.6 alerts, E2.7 export/delete, E2.8 aggregator spike, E3.3 propose-confirm, E3.4 eval suites, E3.5 aggregator impl [gate G2], E4.1–E4.5) follow the same template; their authoritative scope definitions live in `feature-catalog.md` + the architecture docs, and their specs must be written before implementation begins — **the implementation model must never invent product decisions** (all decisions trace to D1–D14 or a new user interview).
