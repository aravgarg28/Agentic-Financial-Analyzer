# Roadmap

Status: Approved for planning. Feature IDs reference `feature-catalog.md`; finding IDs reference `docs/architecture/current-state.md`.

## Recorded interview decisions (D1–D14)

| ID | Decision |
|---|---|
| D1 | US-first, USD home currency; `currency` stored per amount anyway (ISO 4217) |
| D2 | Individual product on a household-ready schema; tenant = `household_id` |
| D3 | CSV-first ingestion in R1; aggregator later behind the same canonical model |
| D4 | Agent: read-only deterministic tools + propose-confirm mutations; no direct model writes |
| D5 | Serious portfolio project + invited beta (<100 users) with real data |
| D6 | **Zero-budget non-negotiable, project-wide** — free tiers only, forever |
| D7 | LLM: best free tier (default Groq Llama 3.3 70B; Gemini free tier as config swap); mandatory data minimization |
| D8 | Hosting: Render free web + Neon/Supabase free Postgres + Upstash free Redis + GitHub Actions; Render free Postgres banned (90-day expiry) |
| D9 | Design scale: 2–3 years history, ~10k transactions/user, imports of low-thousands of rows |
| D10 | Full transactions for checking/savings/credit cards; balance-only for other assets/liabilities |
| D11 | In-app alerts only; email postponed |
| D12 | PDF import: design-only, implement last |
| D13 | Aggregator pulled earlier (R2 design / R3 implementation), contingent on verified-free tier (Teller candidate); slips if not free |
| D14 | Postponed: household UI, investment analytics, multi-currency UX, native mobile, agent scheduled actions |

## Release 0 — Security and correctness foundation *(no new user-facing features)*

**Goal:** the system can be trusted with real financial data. Every "blocks real data" finding is remediated or the code path removed.

- Rebuilt auth: argon2id, server-side sessions, HttpOnly cookies, logout/revocation, login throttling (1.1) — SEC-01/02/03/04/06
- Tenancy: households/memberships bootstrap; **all** endpoints derive tenant from session; client-supplied `user_id` removed everywhere (1.2) — SEC-01, AGT-01/05
- Money → integer minor units + currency; timestamps → timezone-aware; new canonical schema foundations — FIN-01/02/03
- Alembic adopted; destructive seed replaced (21.1, 21.7) — INF-01
- Agent stopgap: tools take tenant from server context only; `update_budget` tool **removed** until propose-confirm exists; raw error leakage stopped — AGT-01/02, INF-06
- CI (lint/type/test/audit/secret-scan), pinned deps + lockfile, backups + restore drill, audit log (auth), structured logging (21.2/21.3/21.4/21.5) — INF-04/06/10
- Free-tier infra migration: Neon/Supabase Postgres, Upstash Redis, corrected render config — INF-02/08, D8
- Truthful naming/docs sweep: net-worth→cash-flow, README corrections, drop unused pgvector — FIN-07, INF-07

**Exit criteria:** tenant-isolation test suite green; zero client-supplied identity; `pip-audit`/`gitleaks` clean; restore drill performed once; real data allowed in.

## Release 1 — Financial-history ingestion

**Goal:** replace manual-only entry with reliable CSV import into a canonical ledger.

- Manual accounts (4.1); canonical transaction ledger (5.1); manual add/edit (5.2)
- CSV import pipeline: upload → mapping (saved presets) → staging → validation → dedup → review → commit → rollback (3.1)
- Category taxonomy + uncategorized as first-class (6.1)
- Onboarding flow + demo mode (1.4, 21.7); audit log extended to imports
- Dashboard rebuilt on the canonical ledger (correct month windows)

**Exit criteria:** 2 years of real history from ≥2 institutions imports correctly; re-import produces zero dupes; rollback verified; fixture corpus in CI.

## Release 2 — Trustworthy financial data and daily utility

**Goal:** the daily-driver money app, all numbers defensible.

- Balance anchors + reconstruction (4.2); balance-only assets/liabilities (4.3)
- Transfer detection (5.3); refund linking (5.5); splits (5.2)
- Rule-based categorization (6.2); recurring detection (7.1)
- Budgets rebuilt (8.1); cash flow (9.1); true net worth (10.1); goals (11.1); reports (15.1)
- In-app alert center (14.1); data export (20.1); account deletion (20.2); uptime monitoring (21.6)
- Aggregator: provider interface designed + free-tier verification spike (2.1 design half of D13)

**Exit criteria:** golden financial-calculation suite green (transfers, refunds, months, balances); export+delete work end-to-end.

## Release 3 — Evidence-backed AI analysis

**Goal:** the AI analyst becomes trustworthy and permission-controlled.

- Agent rebuilt per `agent-design.md`: deterministic read tools, server-injected tenancy, citations on every claim, data minimization to the free LLM, injection defenses, token/loop budgets (17.1, 20.4)
- Propose-confirm actions with audit trail (17.2); agent-proposed categorization (6.3)
- Aggregator implementation if free tier verified (2.1): link, incremental sync, webhooks, reauth, token encryption, disconnect/revocation (20.3); pending→posted reconciliation (5.4)
- Agent eval suite + injection suite in CI

**Exit criteria:** eval ≥95% numeric agreement, injection suite 100%, zero unconfirmed mutations possible by construction.

## Release 4 — Forecasting and scenario planning

- Deterministic cash-flow forecast with per-line explanations (18.1)
- Scenario comparison (19.1); debt payoff planning (12.1)
- OFX/QFX import (3.2); proactive insight feed (17.3)

## R5+ parking lot (designed-for, not scheduled)

PDF import implementation (3.3), household collaboration UI (16), email digests (14.2), MFA (1.5), email password reset (1.3), investment analytics (13.2), multi-currency UX, agent scheduled actions, native mobile.

## Deliberately not in early releases

Features were kept out of R0–R2 on purpose to protect the correctness core: the AI analyst (R3) waits for a defensible ledger; forecasting (R4) waits for recurring detection to mature; the aggregator ships only behind the proven staging/review pipeline and only if free (D6/D13).
