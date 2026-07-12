# Dependency Graph

Status: Proposed. Arrows read "→ blocks". Task IDs from `implementation-tasks.md`; epics from `epics.md`.

## Epic-level graph

```
E0.1 baseline ──► everything (CI gates all merges)
E0.2 schema ──► E0.3 auth ──► E0.4 tenancy ──► every data-touching epic
E0.2 schema ──► E1.1 accounts ──► E1.2 ledger ──► E1.3 CSV import ──► E1.4 onboarding
E0.6 infra/backups ──► real-data use (gates beta invitations, not code)
E0.5 agent stopgap ──► (independent; only needs E0.4)
E0.7 naming sweep ──► (independent)

E1.2 ledger ──► E2.1 balances ──► E2.5 budgets/cashflow(net-worth part)
E1.2 ledger ──► E2.2 transfers/refunds ──► E2.5 cash flow (transfer exclusion)
E1.2 ledger ──► E2.3 rules ──► E1.3 review integration (rules applied at review)
E1.2 ledger ──► E2.4 recurring ──► E2.6 alerts (recurring alerts) ──► E4.1 forecast
E0.4 tenancy ──► E2.7 export/delete
E1.3 import pipeline ──► E2.8 aggregator spike ──► E3.5 aggregator impl (contingent: free tier verified)

E0.4 + E1.2 + E2.x calculators ──► E3.1 agent core ──► E3.2 citations ──► E3.3 propose-confirm ──► E3.4 eval suites
E2.4 recurring + E2.1 balances ──► E4.1 forecast ──► E4.2 scenarios
E2.1 balances ──► E4.3 debt planning
E1.3 pipeline ──► E4.4 OFX/QFX
E3.2 citations + E2.6 alerts ──► E4.5 insight feed
```

## Critical path

**E0.1 → E0.2 → E0.3 → E0.4 → E1.1 → E1.2 → E1.3** — everything else hangs off this spine. Real data may not enter until **E0.\*** is complete (including E0.6 backups) regardless of feature progress.

## Task-level ordering within R0/R1 (IDs from implementation-tasks.md)

```
T-001 pins/lockfile ─► T-002 test harness ─► T-003 CI
T-004 logging/errors/headers (after T-002)
T-005 alembic init ─► T-006 core schema ─► T-007 seed rewrite
T-006 ─► T-010 password+auth endpoints ─► T-011 sessions ─► T-012 throttling
T-011 ─► T-020 principal dependency ─► T-021 endpoint tenancy rewrite ─► T-022 cross-tenant test matrix
T-021 ─► T-030 agent stopgap
T-040 infra migration (Neon/Upstash/Render) ─► T-041 backups+restore drill
T-050 naming/README sweep (anytime after T-021 for endpoint rename)
T-021 ─► T-060 accounts CRUD ─► T-061 ledger endpoints ─► T-062 categories ─► T-063 dashboard rebuild
T-061 ─► T-070 upload+documents ─► T-071 mapping ─► T-072 staging+validation ─► T-073 dedup ─► T-074 review+commit ─► T-075 rollback ─► T-076 fixtures
T-074 ─► T-080 onboarding/demo
```

## Parallelizable lanes (for multiple implementation sessions)

- **Lane A (spine):** T-001…T-022 sequentially.
- **Lane B (infra):** T-040/T-041 after T-003, parallel to auth work.
- **Lane C (agent stopgap + naming):** T-030, T-050 after T-021.
- **Lane D (R1 UI):** frontend pieces of T-063/T-071/T-074 parallel once their API contracts are merged.

## External gates

- **G1 (real data):** all R0 tasks done + restore drill performed once.
- **G2 (aggregator):** Teller (or alternative) free tier verified in writing at implementation time (ADR-04); otherwise E3.5 is unscheduled.
- **G3 (agent GA):** eval suites (numeric/injection/refusal) green in CI (E3.4) before the analyst is enabled for beta users.
