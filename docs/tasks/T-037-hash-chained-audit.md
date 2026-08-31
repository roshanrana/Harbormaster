# T-037 — Hash-chained audit

**Milestone:** M5  **Depends on:** T-007  **Status:** `pending`

## Scope
Only these paths may be touched: `go/internal/audit/`

## Objective
Per-arrival hash chain over decision records, plus a verifier that reports the first break.

## Acceptance criteria
- [ ] record_hash computed exactly as LLD §2.7 specifies
- [ ] `make verify-audit` walks every chain and exits non-zero on a break
- [ ] A deliberately tampered row is detected in a test
- [ ] Any dispatched instruction reconstructable from the chain alone (FR-39)

## Validation
```
make check && make verify-audit
```

## Reference
03-lld.md §2.7, FR-37 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
