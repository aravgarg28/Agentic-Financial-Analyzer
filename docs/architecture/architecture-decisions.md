# Architecture Decision Records

Status: Proposed (each ADR: context → decision → alternatives → consequences). Cross-cutting constraint on every ADR: **zero-budget non-negotiable (D6)** — see ADR-12.

---

## ADR-01 — Modular monolith + one worker (not microservices)
- **Context:** one developer, <100 beta users, free hosting that penalizes many services (independent cold starts, per-service limits). The user's own rules require monolith unless evidence justifies otherwise.
- **Decision:** single FastAPI deployable with internal modules (identity, ledger, ingestion, insights, agent, ops) + one worker process consuming a Postgres job queue. Module boundaries = Python interfaces + table ownership.
- **Alternatives:** microservices (rejected: no deployment-independence or scaling evidence, multiplies free-tier cold starts and operational surface); serverless functions (rejected: long-running imports/agent streams fit poorly, vendor lock-in).
- **Consequences:** simplest ops and testing; extraction seam preserved via module interfaces if ever needed; single DB is both simplification and blast-radius concentration (mitigated by backups + migrations discipline).

## ADR-02 — Sessions: opaque server-side tokens in HttpOnly cookies, stored in Postgres
- **Context:** SEC-02; SPA frontend on a separate subdomain; need revocation.
- **Decision:** 256-bit opaque token, cookie HttpOnly/Secure/SameSite=Lax, server stores token **hash** in `sessions` (Postgres); idle 14d / absolute 30d; logout-everywhere supported.
- **Alternatives:** JWTs (rejected: revocation requires a denylist anyway, footgun surface, no benefit at this scale); Redis-only sessions (rejected: Upstash free-tier eviction could silently log everyone out; Postgres is durable and already backed up).
- **Consequences:** one DB read per request (fine at beta scale; cacheable later); revocation and audit trivially correct.

## ADR-03 — Money: integer minor units (BIGINT cents) + ISO-4217 currency
- **Context:** FIN-01/02; Python/JS float leakage risk.
- **Decision:** `amount_minor BIGINT` + `currency CHAR(3)` everywhere; arithmetic in integers; conversion to display units only at serialization; percentages/rates as integer basis points where stored.
- **Alternatives:** NUMERIC (rejected: correct in Postgres but leaks to binary float through ORMs/JSON unless every path is guarded; integers fail loudly instead of rounding silently); float (rejected outright).
- **Consequences:** trivially exact sums; multi-currency later = new currencies + conversion policy, no schema change; minor-unit exponent handled per-currency (USD=2) at the boundary.

## ADR-04 — Aggregator: provider-agnostic module; Teller as free-tier candidate; feature slips if not free
- **Context:** D13 (user pulled aggregator earlier) vs D6 (zero budget). Plaid production is paid → excluded. Teller has historically offered a free developer tier (US-only, ~100 enrollments); SimpleFIN bridge is low-cost but **not free** → fallback design target only.
- **Decision:** build the provider interface + staging integration generically in R2 design; implement in R3 **only against a verified genuinely-free tier at that time**; otherwise the feature waits. CSV remains the guaranteed path.
- **Alternatives:** commit to Plaid (rejected: cost); scrape banks (rejected: ToS/fragility/credential handling); skip aggregator entirely (rejected: user decision D13).
- **Consequences:** no vendor lock-in (adapter + canonical model); honest risk that the feature slips (documented to user); token security work (encryption, consent, revocation) is provider-independent and reusable.

## ADR-05 — Background jobs: Postgres-backed queue consumed by one worker
- **Context:** imports, syncs, exports, deletion, alert scans need async; zero budget excludes managed queues; Upstash free tier has command limits.
- **Decision:** `jobs` table + `FOR UPDATE SKIP LOCKED` polling worker (either hand-rolled ~200 lines or `procrastinate` [free, Postgres-native] — implementation task decides), transactional enqueue with domain writes, idempotent handlers, retry with backoff + dead-letter status.
- **Alternatives:** Celery+Redis (rejected: broker semantics on free Redis tier are risky, more moving parts); RQ (same concern); cron-only (rejected: no on-demand jobs).
- **Consequences:** exactly-once-ish via idempotency, no extra infra, queue visible in SQL; polling latency (seconds) acceptable for our job types.

## ADR-06 — Canonical transaction model independent of any provider
- **Context:** FIN-05/06; multiple future sources (CSV/OFX/PDF/aggregator).
- **Decision:** single `transactions` schema with provenance, external_id, fingerprint dedup, status pending/posted, transfer/refund links; every source funnels through the same staging pipeline (`ingestion-design.md`).
- **Alternatives:** per-source tables merged at read time (rejected: correctness logic duplicated N times); provider-shaped model (rejected: lock-in, migration pain).
- **Consequences:** dedup/correctness written once; provider adapters stay thin; import rollback and citations fall out of provenance.

## ADR-07 — Vector retrieval: removed until a concrete need exists
- **Context:** pgvector is in the image/deps/README but **unused** (INF-07); no current feature needs semantic retrieval; embeddings of financial data to a free API = another privacy surface (AGT-07).
- **Decision:** drop pgvector from image/deps/docs now; agent context uses deterministic structured data. Reconsider only with a concrete retrieval feature (e.g., semantic merchant search) and a free, private embedding path.
- **Alternatives:** keep it "for later" (rejected: misleading, maintenance surface); local embeddings (deferred: no current need).
- **Consequences:** honest architecture; one less moving part; possible future re-add cost is one migration + dependency (cheap).

## ADR-08 — File storage: Postgres `bytea` for uploaded documents (beta), quota-capped
- **Context:** statements must be retained for provenance; free object storage options (Supabase Storage 1GB, Cloudflare R2 10GB) add another credentialed service; Neon/Supabase free DB storage is limited (~0.5–1GB).
- **Decision:** store originals as `bytea` in `documents` with per-household quota of **10MB** (revised down in adversarial review — free Postgres tiers are ~0.5GB total and the ledger itself needs most of it) and size caps; DB-size watch in ops checklist; revisit to Supabase Storage/R2 if quota pressure appears (interface isolated behind `storage_ref`).
- **Alternatives:** object storage now (viable, deferred: extra service for little gain at beta scale); don't retain originals (rejected: provenance/rollback/audit need them).
- **Consequences:** simplest consistent backup story (files inside pg_dump); DB size watched via ops alert; swap-out path preserved.

## ADR-09 — Agent memory: structured profile + short conversational window (no long-term model-written memory)
- **Context:** AGT-05/07; drift and injection accumulate in model-written memories.
- **Decision:** deterministic regenerated profile (accounts, categories, tz, currency, budgets) + Redis short-term window keyed by session-derived tenant; transcripts persisted for user review only.
- **Alternatives:** model-summarized long-term memory (rejected: injection/drift surface, privacy cost); vector memory (rejected with ADR-07).
- **Consequences:** predictable context size and cost; "remember my preference" features need explicit structured settings later (fine).

## ADR-10 — Agent permissions: read-only tools + typed propose-confirm (D4)
- **Context:** AGT-01/02/03; financial mutations must be user-intended.
- **Decision:** no write tools; closed proposal set executed only via user confirmation through normal authorized endpoints; tenancy injected server-side; citations verified server-side before display.
- **Alternatives:** allowlisted direct writes (rejected: any surviving injection mutates money data); fully read-only (rejected: user chose propose-confirm value).
- **Consequences:** injection blast radius ≈ wrong words, never wrong data; extra UX (confirmation) is a product feature, not friction.

## ADR-11 — Forecasting: deterministic and explainable (no ML)
- **Context:** R4; trust and explainability bar; tiny per-user data volumes.
- **Decision:** projection = confirmed recurring series + trailing category medians + known one-offs; variance bands from simple historical statistics; every projected line carries provenance; scenarios = parameter overlays on the same engine.
- **Alternatives:** ML time-series (rejected: unexplainable at this data volume, no free-tier training/serving win, violates evidence principle).
- **Consequences:** forecasts users can audit line-by-line; accuracy honestly reported via backtests; upgrade path open if evidence demands.

## ADR-12 — Zero-budget vendor policy (constraint elevated to ADR)
- **Context:** user non-negotiable D6.
- **Decision:** every external dependency must have a genuinely free tier covering our use; verification (pricing page check) recorded in the implementing PR; monthly $0 audit in ops checklist. Current approved set: Render (web/worker), Neon **or** Supabase (Postgres), Upstash (Redis), GitHub Actions (CI/backups), Groq/Gemini free tiers (LLM), Teller developer tier (candidate, must re-verify).
- **Consequences:** some features gated on free-tier existence (aggregator); free-tier limits become explicit design inputs (sleep, quotas, rate limits); no vendor can be adopted casually.

## ADR-13 — LLM provider: free tier behind a thin adapter (D7)
- **Context:** Anthropic/OpenAI paid APIs excluded by D6; need tool-calling reliability.
- **Decision:** default Groq (Llama 3.3 70B, free tier, already wired); Gemini free tier as config-swap; adapter confined to one module (no LangChain lock-in decision forced here — implementation task evaluates plain SDK vs LangChain by testability).
- **Consequences:** provider limits shape rate limits (§ security-model 9); privacy handled by minimization (agent-design §8); swap cost is one adapter.

---

## Appendix — Adversarial review log (Phase 6)

Reviewed 2026-07-11 against the challenge list (complexity, premature abstraction, tenant isolation, accounting assumptions, regulatory creep, unbounded AI, failure states, migration risk, lock-in, cost, ops burden, task sizing, verifiable acceptance criteria). Material outcomes:

1. **REVISED — Upstash command budget (failure state / cost).** A Redis-backed limiter on every request would exhaust Upstash's ~10k-commands/day free tier. General/agent limiters moved in-process (single Render instance), login lockout to Postgres; Redis reserved for the chat window. → `security-model.md` §9, T-012.
2. **REVISED — Worker was premature in R1 (complexity).** Synchronous chunked commit handles a 5MB CSV comfortably; the worker now bootstraps in R2 (E2.0) where recurring/alerts/export/delete genuinely need it. `jobs` table still created in T-006 (cheap, dormant). → T-074, epics E1.3/E2.0.
3. **REVISED — Free Postgres storage is the top cost risk.** ~0.5GB total on Neon/Supabase free: 100 users × 10k rows + indexes + `bytea` documents could exceed it. Document quota cut to 10MB/household (ADR-08); DB-size watch added to ops checklist; honest expectation set that the *realistic* beta (~10–20 users) fits. Escalation path: Supabase Storage/R2 for documents, then paid tier is a **user decision**, never assumed (D6).
4. **NOTED — Credit-card balance semantics (accounting).** Balance snapshots for credit accounts represent amount owed (a liability): stored as the provider/statement reports, surfaced with account-type-aware sign in net worth (liability side). Must be specified in E2.1 task specs; recorded in epics E2.1.
5. **NOTED — Uncategorized income (accounting).** Income is category-typed (FIN-06 fix), so uncategorized deposits must appear as an explicit "uncategorized inflow" bucket in cash-flow views — never silently excluded or silently counted as income. Binding on E2.5 task specs and the cash-flow calculator goldens.
6. **NOTED — T-021 sizing (task too large).** The tenancy rewrite may exceed one focused PR; sanctioned split: T-021a insights reads, T-021b budgets/transactions writes, T-021c agent endpoint + Redis keying — each with its slice of the cross-tenant matrix. The split is mechanical; no new decisions required.
7. **CHALLENGED, KEPT — Aggregator design spike in R2 (premature abstraction risk).** Kept because D13 is an explicit user override; scope confined to free-tier verification + interface sketch (no adapter code until G2 passes).
8. **CHALLENGED, KEPT — Postgres sessions (1 read/request).** Trivial at beta scale; durability and revocation correctness outweigh a cache layer's complexity.
9. **CHALLENGED, KEPT — `bytea` documents vs object storage.** One fewer credentialed service and files ride the existing backup; quota + escape hatch documented (see #3).
10. **VERIFIED — No regulatory creep:** beta posture (D5) documented; no money movement, no advice, no third-party data sharing anywhere in the catalog.
11. **VERIFIED — AI boundedness:** budgets, closed toolset, no writes, structural tenancy, CI eval gates (G3) — unbounded-behavior challenge satisfied by construction rather than policy.
12. **VERIFIED — Acceptance criteria are objectively checkable** for all fully-specified tasks (each names a test, command, or grep). R2+ tasks intentionally defer full criteria to release-start spec-writing (recorded rule: implementation model never invents product decisions).
