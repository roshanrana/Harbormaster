# T-007 — Postgres migrations

**Milestone:** G  **Depends on:** T-005  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `go/internal/store/migrations/`

## Objective
Implement the DDL from LLD §6 as ordered, idempotent migrations with an embedded runner.

## Acceptance criteria
- [x] All five tables plus indexes created
- [x] Migrations are idempotent and re-runnable
- [x] A rollback path exists for each migration

## Validation
```
make migrate && make check
```

## Reference
03-lld.md §6 — read only what the criteria above require.

## Handoff notes
Five tables plus schema_migration, embedded FS migration runner, each migration applied with its bookkeeping row in one transaction. Loader refuses any migration missing a rollback half. 6 tests green against real Postgres, including that an exact duplicate violates the uniqueness constraint while a redelivery under a new name does not.
