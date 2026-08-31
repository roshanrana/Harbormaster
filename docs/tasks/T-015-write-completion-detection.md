# T-015 — Write-completion detection

**Milestone:** M1  **Depends on:** T-010  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `go/internal/arrival/`

## Objective
Emit only when a file is fully written: quiet window on size and mtime across two polls, or sentinel present. Rescan and reconcile on restart.

## Acceptance criteria
- [x] A file written in slow chunks emits once, after completion, never mid-write
- [x] Sentinel short-circuits the quiet window
- [x] Kill and restart mid-write produces no duplicate and no loss

## Validation
```
make check && make test-stability
```

## Reference
03-lld.md §5.1, FR-2 — read only what the criteria above require.

## Handoff notes
Quiet-window detection over size and mtime with sentinel short-circuit and restart rescan. A file written in 8 chunks is never emitted mid-stream; ignored suffixes never emit at all. 8 tests using an injected clock.
