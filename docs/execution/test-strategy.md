# Test Strategy

Status: Proposed. Harness lands in T-002; CI gates in T-003. Principle: every audit finding that gets fixed gets a **named regression test** (e.g. `test_sec01_cross_tenant_denied`), so findings cannot silently reopen.

## 1. Unit tests
- Pure logic: money parsing (string→minor units), fingerprint/normalization, date/tz handling, rule engine, recurring cadence math, forecast line generation, amortization, redaction filter, encryption round-trip, session token hashing.
- Fast, no I/O; run on every push.

## 2. API integration tests
- httpx AsyncClient against the real app + disposable Postgres: auth lifecycle, every endpoint's happy path + validation failures + authz failures, CSRF checks (bad Origin rejected), rate limits (429), sanitized errors, pagination.

## 3. Database tests
- Migration up/down for every revision (CI); constraint behavior (unique budget, FK cascades, partial uniques on external_id); household cascade delete leaves zero orphans (query sweep over all tenant tables); `FOR UPDATE SKIP LOCKED` job claiming under concurrency.

## 4. Tenant-isolation tests (the crown jewels)
- T-022 matrix: introspect all routes, two seeded households, assert A's session never sees B's data (404/empty) on every route; unclassified new routes fail CI by design.
- Redis key isolation; agent tool isolation (stub LLM attempting foreign ids); export contains only own household's rows.

## 5. Financial-calculation tests (golden suite)
- Hand-computed fixture households with known answers, asserted cent-exact: category totals, calendar-month boundaries in tz (incl. DST transitions and month-end 23:59 edge), cash flow with confirmed transfers excluded, refund netting conventions, balance reconstruction between anchors, net worth = assets − liabilities, budget vs actual month-to-date, savings-rate division-by-zero and negative-income edges.
- Findings pinned: FIN-01…FIN-09 each has at least one named test.

## 6. Property-based tests (hypothesis)
- Sum of parts == whole for splits; import→export→import idempotence; fingerprint invariance (case/whitespace); minor-unit round-trip through API serialization; aggregation invariance under row order; rollback returns exact prior ledger state.

## 7. Import fixture tests
- T-076 corpus: ≥6 bank-shaped CSVs (+ later OFX with FITID collisions, pathological files: BOM, latin-1, thousands separators, debit/credit columns, parentheses negatives, duplicate rows, overlapping exports) → exact expected canonical ledgers; "already imported" checksum path; quota and size-cap rejections.

## 8. Webhook tests (R3, with aggregator)
- Signature verification (valid/invalid/replayed), unsigned rejection, sync job enqueue idempotence, cursor advancement atomicity, needs_reauth transitions, disconnect deletes tokens (assert ciphertext gone).

## 9. Agent evaluation tests (R3 — agent-design §9)
- **Numeric agreement:** fixture-household Q&A where oracle answers come from the same deterministic calculators; ≥95% agreement required, 100% citation resolvability.
- **Injection suite:** hostile merchant names/descriptions/CSV cells/chat prompts; assert: no mutation possible, no out-of-allowlist tool, no unverified number rendered, no tenant parameter in any tool schema.
- **Refusal suite:** investment-advice and out-of-scope prompts → standard refusal.
- Run in CI with minimal fixture count to stay inside free LLM quotas; full suite nightly.

## 10. Load tests (right-sized for beta)
- Locust/k6 (free, local): 20 concurrent users browsing dashboard + 2 imports + agent queries at rate-limit ceiling against staging; assert p95 latency targets and zero 5xx; job queue drains. No heroic scale targets (D9) — this guards free-tier limits and N+1 regressions.

## 11. Failure-recovery tests
- Kill worker mid-commit → batch stays staged, retry succeeds, no partial ledger rows; LLM provider down → labeled fallback, no fabrication; Redis down → auth still works (sessions in PG), agent/chat degrade gracefully; DB restore drill (quarterly, manual, logged); job retry/backoff/dead-letter paths.

## 12. Browser end-to-end tests (Playwright, free)
- Critical journeys: register→onboard→create account→import CSV via preset→review→commit→dashboard numbers correct; budget set→overspend alert appears with evidence; agent question→cited answer→proposal→confirm→ledger changed + audit visible; export download; account deletion → login impossible, probe finds zero rows.
- Run headless in CI on PRs touching frontend; full matrix nightly.

## 13. Security regression tests
- Named tests per closed finding (SEC-01…INF-10); gitleaks in CI; pip-audit/npm-audit thresholds; headers assertions; upload abuse corpus; error-response internals scan; OpenAPI docs gated in prod config test.

## 14. Meta-rules
- New route ⇒ must be classified in the tenant matrix (enforced by test failure).
- New monetary code path ⇒ golden or property test in same PR (review checklist).
- Every bug fixed ⇒ regression test named after the bug/finding.
- Coverage is tracked but not worshipped; the matrix + goldens + fixtures are the real safety net.
