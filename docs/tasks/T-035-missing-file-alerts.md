# T-035 — Missing-file alerts

**Milestone:** M4  **Depends on:** T-033  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `go/internal/slot/`

## Objective
On deadline expiry with an incomplete slot, emit an alert naming the unmet expectation.

## Acceptance criteria
- [x] Alert names the expectation_id and the missing side
- [x] Fires once per slot, not per poll
- [x] Slot moves to MISSING and stops accepting

## Validation
```
make check
```

## Reference
FR-35 — read only what the criteria above require.

## Handoff notes
Overdue sweep marks slots MISSING so an alert fires once, names the unmet expectation and the missing side.
