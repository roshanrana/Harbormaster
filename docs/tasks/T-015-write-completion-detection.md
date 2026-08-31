# T-015 — Write-completion detection

**Milestone:** M1  **Depends on:** T-010  **Status:** `pending`

## Scope
Only these paths may be touched: `go/internal/arrival/`

## Objective
Emit only when a file is fully written: quiet window on size and mtime across two polls, or sentinel present. Rescan and reconcile on restart.

## Acceptance criteria
- [ ] A file written in slow chunks emits once, after completion, never mid-write
- [ ] Sentinel short-circuits the quiet window
- [ ] Kill and restart mid-write produces no duplicate and no loss

## Validation
```
make check && make test-stability
```

## Reference
03-lld.md §5.1, FR-2 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
