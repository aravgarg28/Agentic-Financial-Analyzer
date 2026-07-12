# Feature Catalog

Status: Approved for planning. Releases: R0–R4 defined in `roadmap.md`; **R5+** = designed-for but explicitly postponed; **EXCLUDED** = will not build.
Every feature lists: problem → behavior → priority → release → dependencies → risks → acceptance criteria → status.

Legend: P1 = must-have for its release, P2 = strongly desired, P3 = opportunistic.

---

## 1. Identity and onboarding

### 1.1 Registration & login (rebuilt) — **Included, R0, P1**
- **Problem:** current auth has no sessions, unsalted SHA-256 passwords, default credentials (SEC-01/02/03/06).
- **Behavior:** email+password registration; argon2id hashing; opaque server-side session token in HttpOnly/Secure/SameSite=Lax cookie; logout revokes server-side; sessions expire (idle 14d, absolute 30d); login throttling per-account and per-IP; uniform error messages (no enumeration).
- **Dependencies:** sessions table, household bootstrap (1.2). **Risks:** cookie handling across Render subdomains (document CORS+cookie config explicitly).
- **Acceptance:** cross-user request with valid session for user A against user B's data returns 404/403 in automated test; password hashes verified argon2id; logout invalidates immediately; 10 failed logins → throttle.

### 1.2 Household bootstrap (invisible) — **Included, R0, P1**
- **Problem:** retrofitting tenancy is expensive (D2).
- **Behavior:** signup creates a `household` with one `membership(role=owner)`; every domain row is scoped by `household_id` derived from the session. No household UI.
- **Acceptance:** no query path accepts client-supplied tenant identifiers (verified by code search + tests).

### 1.3 Password reset — **Included (manual path) R0; email-based R5+**
- **Behavior R0:** no self-serve reset (no free email dependency yet); operator-assisted reset documented; account lockout requires operator. **R5+:** email-based reset when email epic lands.
- **Risks:** beta users locked out → operator burden; acceptable at <100 users.

### 1.4 Onboarding flow — **Included, R1, P2**
- **Behavior:** first-run checklist: create account(s) → import CSV → review → see dashboard. Empty states explain what to do next.
- **Acceptance:** new user reaches a populated dashboard without documentation.

### 1.5 MFA/TOTP — **Postponed R5+.** Free (pyotp), but adds recovery-flow complexity before it pays off at beta scale.

## 2. Financial connections (aggregator)

### 2.1 Provider-agnostic connection module — **Included, R2 (design) / R3 (implementation), P2** (D13)
- **Problem:** manual CSV import is periodic labor; users want auto-sync.
- **Behavior:** `connections` module with a provider interface (link, list accounts, fetch transactions since cursor, webhook verify, reauth). Candidate provider: Teller (free developer tier, US-only — **must be re-verified as free at implementation time**; SimpleFIN as fallback). Provider tokens encrypted at the application layer; connection health surfaced; reauth flow; incremental sync via worker.
- **Dependencies:** canonical ingestion pipeline (R1), worker, staging/dedup reuse. **Risks:** free tier disappears → feature slips (zero-budget rule wins, D6); webhook auth mistakes; provider data quality.
- **Acceptance:** sandbox-linked account syncs into staging → review → commit path identical to CSV; revoking consent deletes tokens and halts sync; all webhook payloads signature-verified.

## 3. File imports

### 3.1 CSV import — **Included, R1, P1** (D3)
- **Behavior:** upload CSV (size/type limited) → parse with encoding sniffing → column-mapping UI with per-institution **saved mappings** → staging table with per-row validation (date parse, amount parse, sign convention, currency default USD) → dedup detection (exact fingerprint + near-dup review) → user reviews & commits → batch becomes transactions with provenance. Batch **rollback** deletes exactly its committed rows.
- **Risks:** bank CSV dialect chaos (mitigate: fixture corpus per institution; mapping presets); duplicated overlapping exports (mitigate: fingerprint dedup + review).
- **Acceptance:** fixture suite (≥6 real-world bank formats) imports correctly; re-importing the same file yields 0 new transactions; rollback restores prior state exactly (verified by checksum of ledger).

### 3.2 OFX/QFX import — **Included, R4, P2.** Same staging pipeline; FITID used as strong dedup key. Acceptance: fixture OFX imports; FITID collision handling tested.

### 3.3 PDF statement import — **Design-only now; implementation R5+** (D12)
- **Behavior (designed):** extract candidate rows (pdfplumber/camelot, free) → stage with **mandatory human review of every row** → commit. LLM never produces authoritative amounts.
- **Acceptance (future):** zero rows committed without explicit review.

## 4. Accounts and balances

### 4.1 Manual accounts — **Included, R1, P1** (D10)
- **Behavior:** create checking/savings/credit-card accounts (institution label, type, currency, display name); every transaction belongs to an account.
- **Acceptance:** transactions cannot exist without an account; account archive hides but preserves history (soft delete).

### 4.2 Balance anchors & reconstruction — **Included, R2, P1**
- **Problem:** transaction sums alone drift from reality.
- **Behavior:** user enters statement balances as dated **balance snapshots** (anchors); system reconstructs running balance between anchors and flags discrepancies (missing/duplicate transactions).
- **Acceptance:** golden tests reconstruct balances to the cent; discrepancy alert fires on injected gap.

### 4.3 Balance-only assets/liabilities — **Included, R2, P2** (D10): manually updated snapshots for investments, loans, property, cash; feed net worth only.

## 5. Transactions and reconciliation

### 5.1 Canonical transaction ledger — **Included, R1, P1**
- **Behavior:** provider-independent transaction model (see `data-model.md`): minor-unit amount + currency, posted/pending status, account FK, merchant link, category, provenance, soft delete, audit trail on edits.
- **Acceptance:** property-based tests on sign/rounding; all reads tenant-scoped.

### 5.2 Manual add/edit/split — **Included, R1 (add/edit), R2 (split), P1/P2.** Edits tracked (audit event); splits sum exactly to parent amount (enforced).

### 5.3 Transfer detection — **Included, R2, P1**
- **Problem:** transfers between own accounts double-count as income+expense (FIN-06).
- **Behavior:** heuristic matching (opposite amounts, ±3 days, cross-account) proposes transfer pairs; user confirms; confirmed pairs excluded from income/spending aggregates.
- **Acceptance:** golden dataset with transfers yields correct cash flow; unconfirmed candidates clearly flagged.

### 5.4 Pending→posted reconciliation — **Included, R3 (with aggregator), P2.** Pending rows replaced by posted matches without duplication; CSV imports are posted-only.

### 5.5 Refund linking — **Included, R2, P3.** Optional link refund→original purchase; aggregates can net or show gross (defined convention: gross by default, netting visible per merchant).

## 6. Categorization

### 6.1 Category taxonomy — **Included, R1, P1.** System defaults + user categories (hierarchical, 2 levels max). Uncategorized is a first-class visible state, never silently guessed.
### 6.2 Rule-based auto-categorization — **Included, R2, P1.** User-defined rules (merchant contains / amount range / account) applied at import review-time; rules are ordered, deterministic, and previewable. Acceptance: same input + rules = same output, always.
### 6.3 Agent-proposed categorization — **Included, R3, P2** (D4). Agent proposes category for uncategorized rows with reasoning; user confirms in bulk UI; confirmations can be promoted to rules. LLM proposal ≠ committed data until confirmed.

## 7. Recurring payments

### 7.1 Recurring series detection — **Included, R2, P1.** Deterministic detection (same merchant fingerprint, near-equal amount, regular cadence); user confirms series; tracks next-expected date/amount, missed and price-increased occurrences.
- **Acceptance:** fixture corpus (subscriptions, salaries, rent with drift) detected at ≥90% precision; every detected series lists its member transactions (evidence).

## 8. Budgets

### 8.1 Category budgets (rebuilt) — **Included, R2, P1.** Monthly budgets per category in minor units, calendar-month windows in the user's timezone (fixes FIN-03/09), rollover optional, budget vs actual with drill-down to transactions. Unique (household, category, month) constraint; upsert semantics (fixes FIN-08/10).

## 9. Cash flow

### 9.1 Cash-flow view — **Included, R2, P1.** Calendar-month income/spend/net with transfer exclusion, drill-down, and correct month boundaries (fixes FIN-04/07 mislabeling). Income = category-typed, not amount>0 (fixes FIN-06).

## 10. Net worth

### 10.1 True net worth — **Included, R2, P1.** Assets (account balances from anchors+reconstruction, balance-only assets) minus liabilities (credit balances, loans) over time; clearly distinct from cash flow. Replaces the mislabeled `/analytics/net-worth` (FIN-07).

## 11. Goals

### 11.1 Savings goals — **Included, R2, P3.** Target amount+date, linked account(s), progress from balances, on/off-track vs required monthly saving. Deterministic math only.

## 12. Debt

### 12.1 Debt tracking & payoff plans — **Included, R4, P2.** Liabilities with APR/minimum payment; avalanche/snowball projections (deterministic amortization); payoff-date and interest-cost comparisons. Not advice — labeled as arithmetic projections.

## 13. Investments

### 13.1 Balance-only investment tracking — **Included, R2 (as 4.3), P2.**
### 13.2 Holdings/positions/price analytics — **Postponed R5+** (D14). Requires free price data vetting and a full asset model; excluded from early releases.

## 14. Alerts

### 14.1 In-app alert center — **Included, R2, P1** (D11)
- **Behavior:** alerts for budget threshold/overrun, upcoming & missed recurring, balance-reconstruction discrepancy, large/anomalous transaction (deterministic z-score per category), import completed/failed. Every alert carries: what fired, the rule/threshold, and links to evidence rows. Read/dismiss state; per-type mute.
- **Acceptance:** each alert type has a fixture that triggers it and a test asserting its evidence links resolve.
### 14.2 Email digests — **Postponed R5+** (D11).

## 15. Reports

### 15.1 Monthly/annual summaries — **Included, R2, P2.** Month and year in review: category totals, top merchants, cash flow, net-worth delta; all figures drill down. CSV export of any report table.

## 16. Household collaboration — **Postponed R5+** (D14). Schema-ready (households/memberships/roles) from R0; invitations, shared visibility, roles UI deliberately deferred.

## 17. AI analyst

### 17.1 Evidence-backed Q&A — **Included, R3, P1** (D4, D7)
- **Behavior:** chat over the user's own data; deterministic tenant-scoped read tools; every numeric claim computed by code with citation chips resolving to transactions/aggregates; refuses questions outside data scope; refuses personalized investment/tax advice with a standard message.
- **Acceptance:** eval set where expected answers are computed deterministically — ≥95% numeric agreement; 100% citation resolvability; injection suite passes (see `agent-design.md`).
### 17.2 Propose-confirm actions — **Included, R3, P1** (D4). Agent emits typed proposals (recategorize, set budget, confirm transfer pair, confirm recurring series); UI confirmation executes via normal authorized API; full audit trail (proposed→confirmed/rejected).
### 17.3 Proactive insight feed — **Included, R4, P3.** Insights are deterministic detectors narrated by the model, never model-invented claims.
### 17.4 Agent-initiated scheduled actions — **Postponed R5+** (D14).

## 18. Forecasting

### 18.1 Cash-flow forecast — **Included, R4, P1.** Deterministic 1–12 month projection: confirmed recurring series + trailing category medians + known one-offs; per-line explanation of every projected item; confidence bands from historical variance (simple statistics, no ML).
- **Acceptance:** backtest on fixture history: median absolute error reported and displayed honestly in UI; every projected line item traceable to its source series/statistic.

## 19. Scenario planning

### 19.1 Scenario comparison — **Included, R4, P2.** Parameterized deterministic simulations layered on the forecast: "drop subscription X", "rent +$300", "extra $200/mo to debt Y", "one-time $3k purchase in March". Side-by-side cash-flow/net-worth/payoff-date deltas. Scenarios are saved, named, and re-runnable.

## 20. Privacy controls

### 20.1 Data export — **Included, R2, P1.** Full export: transactions/accounts/budgets/rules/alerts as CSV+JSON zip, generated by worker, downloadable in-app.
### 20.2 Account deletion — **Included, R2, P1.** Hard delete of all household data (rows, files, Redis keys, audit anonymization policy defined); irreversible with typed confirmation; completes within 24h (worker) with in-app confirmation.
### 20.3 Connection disconnect & token revocation — **Included with 2.1 (R3), P1.** Disconnect deletes provider tokens immediately; user chooses keep-or-delete for already-imported data.
### 20.4 LLM data-minimization control — **Included, R3, P1** (D7). Documented and enforced boundary: model receives only aggregates + cited rows needed for the question; a per-household toggle disables the AI analyst entirely.

## 21. Administration and operations

### 21.1 Migrations (Alembic) — **Included, R0, P1** (INF-01). All schema changes via migrations; CI enforces no-drift.
### 21.2 CI pipeline — **Included, R0, P1** (INF-04). GitHub Actions (free): lint, type-check, tests, dependency audit (pip-audit/npm audit), secret scanning (gitleaks), migration check.
### 21.3 Backups & restore drill — **Included, R0, P1** (INF-10). Nightly encrypted pg_dump via GitHub Actions to a private artifact/storage (free), documented restore procedure, **quarterly restore drill** required.
### 21.4 Audit log — **Included, R0 (auth events) → R1+ (imports, mutations, agent proposals), P1.** Append-only audit_events table.
### 21.5 Structured logging & error handling — **Included, R0, P1** (INF-06). Request IDs, no PII/secrets in logs, sanitized client errors.
### 21.6 Monitoring/uptime — **Included, R2, P3.** Free uptime pinger + in-repo status doc; Render/Neon dashboards. (Also mitigates free-tier sleep.)
### 21.7 Seed/demo data — **Included, R1, P3.** Demo mode seeds a **demo household** only; never drops tables (fixes INF-01 destructive seed); disabled in production.

---

## Explicitly EXCLUDED (will not build)
- Money movement of any kind (payments, transfers, bill pay).
- Personalized investment/tax/legal advice.
- Third-party data sharing, ads, or analytics resale.
- Model-generated SQL against the database (agent uses typed tools only).
- Native mobile apps (responsive web only) — reconsider post-R4.
