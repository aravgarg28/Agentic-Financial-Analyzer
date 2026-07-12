# Migration Plan

Status: Proposed. How to move from the prototype schema/data to the target model safely.

## 0. Honest starting position

There is **no production deployment and no real user data**. The only existing data is randomly generated seed data (`seed.py`) plus possibly hand-entered dev rows — all reproducible, none authoritative. This changes the migration calculus fundamentally: we do **not** need compatibility shims for prototype data; we need a **disciplined path that would have been safe** and that becomes binding the moment real data exists (post-G1).

## 1. Alembic adoption (T-005)

1. `alembic init` with the async template; configure from `settings.database_url`.
2. **Baseline revision** `0001_prototype_baseline`: captures the current 3-table schema exactly, so any existing dev DB can be stamped (`alembic stamp 0001`) and upgraded from there — no dev environment is orphaned.
3. Remove `Base.metadata.create_all` from application startup; schema changes henceforth ONLY via migrations.
4. CI: `alembic upgrade head` against a fresh Postgres + drift check (autogenerate produces empty diff against models) on every PR.

## 2. Prototype → target schema (T-006)

- Revision `0002_core_target_schema`:
  - Create `households, memberships, sessions, audit_events, jobs`.
  - Recreate `users` (email CITEXT, argon2 fields, status) — old users **dropped**, not migrated: passwords are unsalted SHA-256 (SEC-03) and must not be carried forward; usernames aren't emails; all current users are dev fixtures.
  - Create new `accounts, categories, transactions, budgets` per `data-model.md` (minor units, FKs, uniques).
  - Drop prototype `transactions`/`budgets`.
- **Explicit data decision:** prototype data is sanctioned as disposable (recorded here; the seed can regenerate demo data via T-007). If anyone has meaningful hand-entered dev data, export it to CSV first — it can re-enter through the R1 import pipeline, which is a better test of that pipeline than any backfill script.
- Downgrade path recreates the prototype tables (empty) so `downgrade` is structurally sound even though data is not round-tripped (documented in the revision docstring).

## 3. Float → minor units (policy, not backfill)

- No float amounts survive: the new schema starts in minor units, and the ingestion pipeline parses text→integer directly (never through float).
- **Had** real float data existed, the procedure (recorded for the future): `ROUND(amount::numeric * 100)::bigint` with a pre/post audit query comparing `SUM(amount::numeric)` vs `SUM(amount_minor)/100.0` per account, manual review of any row where `ABS(amount*100 - ROUND(amount*100)) > 0.001`. This template applies to any future precision-affecting change.

## 4. R1+ incremental migrations

Each feature revision follows the same contract:
- Additive first (new tables/columns nullable or defaulted), destructive later (separate PR, after a compatibility period; a "compatibility period" during beta = at least one deploy cycle with both paths verified).
- Down-revision tested in CI (up→down→up).
- Data transformations idempotent and re-runnable (guard queries).
- **Verification queries** shipped in the migration docstring (e.g., after transfers table lands: `SELECT COUNT(*) FROM transactions t JOIN transfers tr ON t.transfer_id = tr.id WHERE tr.status <> 'confirmed'` must be 0).

## 5. Post-G1 rules (once real data exists)

- Every migration PR must state: tables touched, lock behavior (Neon/Supabase free tier = small instance; avoid long `ACCESS EXCLUSIVE` rewrites — batch backfills in keyed chunks), rollback procedure, and the verification queries run after deploy.
- Nightly backup (T-041) must be < 24h old before any destructive migration; operator confirms by checking the latest artifact timestamp.
- Restore drill required within the quarter of any major schema change.

## 6. Endpoint & field deprecations

| Obsolete | Fate | When |
|---|---|---|
| `user_id` query/body params (all routes) | **Removed** (not deprecated — they are the vulnerability, SEC-01) | T-021 |
| `POST /auth/register`,`/login` response bodies returning `user_id` | Replaced by cookie session + profile endpoint | T-011 |
| `/analytics/net-worth` | Renamed to `/insights/cash-flow`; true net worth arrives in R2 as `/insights/net-worth` | T-021/T-050, E2.1 |
| `/analytics/*` (month_offset/days semantics) | Rebuilt as `/insights/*` with explicit month + tz semantics | T-021 |
| Agent tools `update_budget`, model-visible `user_id` params | Removed | T-030 |
| `app/seed.py` (drop_all) | Replaced by `scripts/seed_demo.py` | T-007 |
| pgvector image + dependency | Removed (ADR-07) | T-001/T-050 |
| In-memory `RateLimitMiddleware` | Replaced by Redis-backed dependency | T-012 |

Because the frontend is part of the same repo and deploys with the API, no external API consumers exist → breaking changes within a release are acceptable **until** G1; afterward, breaking changes require a frontend+backend synchronized deploy note in the PR.

## 7. Rollback procedures

- **Schema:** every revision's `downgrade()` tested in CI; operational rollback = deploy previous image + `alembic downgrade <rev>` (order: app first if change was additive, migration first if destructive — stated per PR).
- **Data:** restore from encrypted nightly dump into a scratch DB, verify with row-count + checksum queries, then swap connection string (documented in `docs/ops/restore.md`, drilled quarterly).
- **Feature:** environment-flag kill switches for agent endpoints and imports (config, free) so a misbehaving subsystem can be disabled without a deploy.
