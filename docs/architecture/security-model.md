# Security Model

Status: Proposed. Remediates the audit register in `current-state.md` (SEC-*, AGT-*, INF-*). Constraint: everything must run on free tiers (D6), so controls are architectural and procedural, not purchased.

## 1. Authentication

- **Credentials:** email + password. Passwords hashed with **argon2id** (via `argon2-cffi`), per-password salt, tuned params documented in code. Legacy SHA-256 hashes (if any user data is migrated) are invalidated — users re-register or use the operator reset path; we do NOT carry weak hashes forward (SEC-03).
- **Password policy:** minimum 10 chars, checked against a small common-password list (free, local); no composition theater.
- **Login throttling (SEC-04):** per-account exponential backoff after 5 failures (`failed_login_count`, `locked_until`) + per-IP limiter (Upstash Redis, fixed window). Uniform error message for wrong-user/wrong-password. Registration returns a uniform response to prevent enumeration.
- **Reset (SEC-05):** R0 = operator-assisted (documented manual procedure, identity verified out-of-band; acceptable at <100 invited users). Email-based reset arrives with the email epic (R5+).

## 2. Sessions (SEC-02)

- Opaque 256-bit random token, stored client-side in an **HttpOnly, Secure, SameSite=Lax cookie**. Server stores only `token_hash` (SHA-256 of token) in the `sessions` table — DB disclosure does not yield usable tokens.
- Idle expiry 14 days (sliding `idle_expires_at`), absolute expiry 30 days. Logout revokes server-side (`revoked_at`). "Log out everywhere" revokes all user sessions.
- Session fixation: token is issued only after successful authentication; any pre-auth cookie is discarded.
- Cross-site: frontend and API live on different Render subdomains → CORS allows exactly the frontend origin with `credentials: true`; cookie set by the API domain; CSRF defense below.

## 3. CSRF

- SameSite=Lax blocks most cross-site POSTs. Because the frontend origin differs from the API origin, all state-changing endpoints additionally require a custom header (`X-Requested-With`) which cross-origin forms cannot set and CORS restricts, plus `Origin` header validation against the allowlist. (Double-submit token unnecessary given this combination; revisit if cookie scope changes.)

## 4. Authorization & tenant isolation (SEC-01, AGT-01, AGT-05)

- Every request resolves `Principal{user_id, household_id, role}` from the session. **No endpoint, query param, body field, or agent tool accepts a client- or model-supplied tenant identifier.** The old `user_id` params are removed, not deprecated.
- Data access goes through module interfaces that require a `Principal` and apply `WHERE household_id = :hid` unconditionally. A repo-wide test enumerates all routes and asserts cross-tenant requests return 404 (not 403, to avoid resource-existence leaks via IDs; public_ids are UUIDs so enumeration is impractical anyway).
- Roles (owner/member/viewer) exist in schema; beta enforces owner-only. Authorization checks are centralized (dependency), not per-route ad hoc.

## 5. Secret management

- Secrets only in environment variables (Render dashboard / local `.env` which stays gitignored — INF-09). `gitleaks` in CI prevents regressions. Key inventory: DB URL, Redis URL, LLM API key, `TOKEN_ENCRYPTION_KEY`, session pepper (optional). Rotation procedure documented per key (all are single-service, rotate-and-redeploy).

## 6. Encryption

- **In transit:** TLS everywhere (Render/Neon/Upstash all provide TLS on free tiers); HSTS header set.
- **At rest:** managed-provider disk encryption (Neon/Supabase default). **Application-layer encryption** additionally for high-value fields: aggregator `access_token_encrypted` uses AEAD (e.g., `cryptography` Fernet/AES-GCM) with `TOKEN_ENCRYPTION_KEY` from env; nonce per token. Documents (statements) stored with checksum; if stored in DB `bytea` (ADR-08) they inherit at-rest encryption; app-layer encryption for PDFs considered in the same ADR.
- Backups are **encrypted before leaving the runner** (age/gpg symmetric key held only in GitHub Actions secrets + operator password manager).

## 7. Provider-token storage (aggregator, R3)

- Tokens never plaintext in DB, never logged, never serialized to the client, decrypted only in the worker/API process at the moment of provider calls. Disconnect (20.3) deletes ciphertext immediately and writes an audit event; consent record marked revoked.

## 8. Audit logging (INF-06, 21.4)

- Append-only `audit_events`: register/login/logout/failed-login/lockout, session revocation, imports (staged/committed/rolled back), financial mutations (create/edit/delete/recategorize/transfer-confirm), agent proposals + confirmations/rejections, exports, deletions, connection link/disconnect, consent grant/revoke, operator actions.
- Events carry actor, action, target type + public_id, request_id, timestamp; **no secrets, no full financial payloads**. Written in the same transaction as the mutation where feasible.

## 9. Rate limiting (SEC-04, INF-05)

- Limiter as a route dependency returning proper `429` + `Retry-After` (not a BaseHTTPMiddleware raise, which surfaces as 500 — INF-05).
- **Store choice (revised in adversarial review):** Upstash free tier allows on the order of 10k commands/day — a Redis check on every request would exhaust it. Since Render free tier runs a **single instance**, the general and agent limiters are **in-process** (bounded LRU of ip/user windows — also fixes the unbounded-dict growth from INF-05); login lockout is **Postgres-backed** (`failed_login_count`/`locked_until`, durable across restarts). Redis is reserved for the agent chat window. If the app ever scales past one instance, the limiter store swaps behind the same dependency interface.
- Scopes: login 5/15min/account (DB) + 20/hr/IP, register 5/hr/IP, agent 30/min/user (also protects the free LLM quota), imports per-user, general API loose. Limits are config, documented.

## 10. File security (imports)

- Size cap, extension + MIME allowlist (`text/csv`, OFX types, `application/pdf` later), content parsed with hardened parsers, never executed or reflected; filenames sanitized/stored as metadata only; documents served only via authenticated download with `Content-Disposition: attachment` + `X-Content-Type-Options: nosniff`. Upload endpoints rate-limited; per-household storage quota (free-tier DB space is finite).

## 11. Application-security headers & misc (INF-06)

- Middleware sets: `Strict-Transport-Security`, `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, minimal CSP for the API (frontend CSP handled in Next config). Error handler returns sanitized messages + request_id; details go to server logs only (fixes raw `str(e)` streaming). OpenAPI docs disabled or auth-gated in production.

## 12. Dependency & supply-chain security (INF-04)

- Backend: pinned versions + committed lockfile (poetry.lock). Frontend: package-lock committed (already true). CI runs `pip-audit` + `npm audit --audit-level=high` + `gitleaks`; Dependabot (free) for update PRs. Docker base images pinned by digest.

## 13. Logging & redaction

- Structured JSON logs with request_id and principal public_id (never email), no financial amounts in access logs, no tool payloads at info level, secrets redacted by a filter. LLM prompts/responses logged only in explicit debug mode, never in production (AGT-07).

## 14. Backup & recovery (INF-10)

- Nightly GitHub Actions workflow: `pg_dump` → compress → **encrypt** → upload to private artifact/storage (free); 14-day retention rolling. Restore procedure documented step-by-step; **quarterly restore drill** into a scratch Neon branch/database is a standing calendar task; drill outcome recorded in repo.

## 15. Account deletion & data export (20.1/20.2)

- **Export:** worker job produces a zip (CSV + JSON of all household entities), stored briefly, downloaded via authenticated link, then purged.
- **Deletion:** typed confirmation → worker `account_delete` job: revoke connections/tokens, delete documents, cascade-delete household (FK design makes this one root delete), purge Redis keys, revoke sessions, write final audit event with anonymized actor, done within 24h. Verified by a post-delete probe (no rows remain for household id).

## 16. Consent revocation

- `consent_records` track aggregator and LLM-processing consents; revoking aggregator consent = disconnect flow; revoking LLM consent = AI features disabled for the household immediately (20.4); both audited.

## 17. Threat model (summary)

Assets: financial history, credentials, provider tokens, LLM key.
Adversaries & mitigations:
- **Remote attacker (no account):** TLS, no exposed datastores, rate limits, no default creds (SEC-06), uniform auth errors.
- **Malicious/curious user (has account):** structural tenant isolation, UUID public ids, 404-on-foreign-resource, per-user rate limits, audit trail.
- **Prompt injector (via imported data or chat):** agent cannot write; tenant never model-controlled; tool results fenced as data; injection eval suite (see `agent-design.md`).
- **Stolen device/cookie:** HttpOnly+Secure, idle/absolute expiry, logout-everywhere, session hash storage.
- **DB disclosure (backup leak, provider breach):** argon2id hashes, hashed session tokens, encrypted provider tokens, encrypted backups.
- **Supply chain:** pinned deps, audits in CI, digest-pinned images.
- **Operator error:** migrations-only schema changes, non-destructive seed, restore drills, destructive actions gated + audited.
Out of scope (accepted for beta): nation-state attackers, malicious insiders at Neon/Upstash/Render/Groq (mitigated only by minimization + encryption of highest-value fields), DoS beyond free-tier rate limiting.

## 18. Security test plan

- **Unit:** hashing, session issuance/expiry/revocation, limiter, encryption round-trip, redaction filter.
- **Integration (CI):** cross-tenant matrix over every route (A's session vs B's resources → 404); auth lifecycle; CSRF (cross-origin POST rejected); rate-limit returns 429; upload abuse (oversize, wrong type, malformed CSV); error responses contain no internals.
- **Agent security suite:** injection corpus (direct + data-embedded) asserting: no tenant escape, no mutation, no tool outside allowlist, no instruction-following from tool results (details in `agent-design.md`).
- **Regression:** every closed SEC/AGT/FIN/INF finding gets a pinned test named after its ID.
- **Periodic manual:** quarterly restore drill; quarterly dependency/key review; pre-release OWASP-top-10 checklist pass.
