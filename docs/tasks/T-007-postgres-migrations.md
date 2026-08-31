# T-007 — Postgres migrations

**Milestone:** G  **Depends on:** T-005  **Status:** `pending`

## Scope
Only these paths may be touched: `go/internal/store/migrations/`

## Objective
Implement the DDL from LLD §6 as ordered, idempotent migrations with an embedded runner.

## Acceptance criteria
- [ ] All five tables plus indexes created
- [ ] Migrations are idempotent and re-runnable
- [ ] A rollback path exists for each migration

## Validation
```
make migrate && make check
```

## Reference
03-lld.md §6 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
