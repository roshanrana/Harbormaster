# T-037 — Hash-chained audit

**Milestone:** M5  **Depends on:** T-007  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `go/internal/audit/`

## Objective
Per-arrival hash chain over decision records, plus a verifier that reports the first break.

## Acceptance criteria
- [x] record_hash computed exactly as LLD §2.7 specifies
- [x] `make verify-audit` walks every chain and exits non-zero on a break
- [x] A deliberately tampered row is detected in a test
- [x] Any dispatched instruction reconstructable from the chain alone (FR-39)

## Validation
```
make check && make verify-audit
```

## Reference
03-lld.md §2.7, FR-37 — read only what the criteria above require.

## Handoff notes
Per-arrival hash chain with Verify and VerifyAll. Tamper and deletion both detected and localised to the offending record. Timestamps truncated to Postgres precision; inputs/outcome stored as TEXT so hashed bytes equal stored bytes. 6 tests.
