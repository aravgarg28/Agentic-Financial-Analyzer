# Epics

Status: Proposed. Epics group `implementation-tasks.md` tasks; ordering constraints in `dependency-graph.md`. Release mapping per `docs/product/roadmap.md`.

## Release 0 — Security & correctness foundation

- **E0.1 Engineering baseline** — pinned deps + lockfile, test harness, CI (lint/type/test/pip-audit/npm-audit/gitleaks), structured logging, sanitized errors, security headers. *(INF-04/06)*
- **E0.2 Migrations & schema foundation** — Alembic adoption; new core schema (households, users, memberships, sessions, accounts, transactions, categories, budgets, audit_events, jobs) per `data-model.md`; non-destructive demo seed. *(INF-01, FIN-01/02/08 foundations)*
- **E0.3 Authentication & sessions** — argon2id, register/login/logout, session cookies, throttling, uniform errors, audit of auth events. *(SEC-01…06)*
- **E0.4 Tenant isolation** — Principal dependency, household bootstrap, all endpoints rewritten to session-derived tenancy, client `user_id` params removed, cross-tenant test matrix. *(SEC-01, AGT-05)*
- **E0.5 Agent stopgap** — remove `update_budget` tool, strip model-supplied tenant args, tenancy injected server-side, sanitized agent errors, bounded tool output. *(AGT-01/02/06 interim; full rebuild is R3)*
- **E0.6 Free-tier infrastructure & backups** — Neon/Supabase + Upstash migration, corrected Render config, nightly encrypted backups + documented restore, uptime pinger, $0 audit checklist. *(INF-02/08/10, D8)*
- **E0.7 Truthful naming & docs sweep** — net-worth→cash-flow rename, README corrections, remove pgvector. *(FIN-07, INF-07, ADR-07)*

## Release 1 — Financial-history ingestion

- **E1.1 Accounts & institutions** — manual accounts CRUD, institutions, archive semantics.
- **E1.2 Canonical ledger** — transactions table live, manual add/edit with audit, category taxonomy + uncategorized, corrected dashboard analytics (calendar months, tz).
- **E1.3 CSV import pipeline** — upload + documents, mapping UI + saved presets, staging + validation, dedup engine, review UX, synchronous chunked commit/rollback, fixture corpus. *(No worker in R1 — adversarial-review revision.)*
- **E1.4 Onboarding & demo mode** — first-run flow, demo household seed, empty states.

## Release 2 — Trustworthy data & daily utility

- **E2.0 Worker bootstrap** — `python -m app.worker` polling the `jobs` table (ADR-05); first consumers: recurring detection, alert scans, export, delete. *(Moved here from R1 in adversarial review.)*
- **E2.1 Balances & net worth** — balance snapshots/anchors, reconstruction + discrepancy detection (credit-card accounts: balance stored as signed liability, sign semantics defined per account type), balance-only assets/liabilities, true net worth view.
- **E2.2 Transaction intelligence** — transfer detection (candidate→confirm), refund linking, splits.
- **E2.3 Categorization rules** — deterministic rule engine + preview, rule management UX.
- **E2.4 Recurring detection** — detector job, confirm UX, series tracking.
- **E2.5 Budgets & cash flow** — budgets rebuilt (calendar month, unique constraints, upsert), cash-flow view, reports (month/year), goals.
- **E2.6 Alert center** — deterministic alert scans + evidence links, alert UX, mute/read states.
- **E2.7 Privacy controls** — full export job, hard-delete account job, verified post-delete probe.
- **E2.8 Aggregator design spike** — provider interface, Teller free-tier verification, token-encryption utilities. *(design half of D13)*

## Release 3 — Evidence-backed AI analysis

- **E3.1 Agent core rebuild** — provider adapter, orchestration loop with budgets, deterministic read tools over calculators, structured profile + Redis window. *(agent-design §2–3, §7)*
- **E3.2 Citations & verification** — answer schema, server-side claim verification, citation UI. *(agent-design §4)*
- **E3.3 Propose-confirm** — proposal objects, confirmation UX, execution via authorized endpoints, audit trail. *(D4)*
- **E3.4 Injection defenses & eval** — data fencing, redaction, injection/numeric/refusal suites in CI. *(agent-design §5, §9)*
- **E3.5 Aggregator implementation** *(contingent, ADR-04)* — Teller adapter, link/sync/webhooks/reauth, pending→posted reconciliation, disconnect+revocation.

## Release 4 — Forecasting & planning

- **E4.1 Forecast engine** — deterministic projection + provenance, backtest harness, forecast UI.
- **E4.2 Scenarios** — parameter overlays, comparison UI, saved scenarios.
- **E4.3 Debt planning** — liabilities, amortization projections, payoff comparisons.
- **E4.4 OFX/QFX import** — parser + FITID dedup into existing pipeline.
- **E4.5 Insight feed** — deterministic detectors narrated with citations.
