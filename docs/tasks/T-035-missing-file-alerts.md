# T-035 — Missing-file alerts

**Milestone:** M4  **Depends on:** T-033  **Status:** `pending`

## Scope
Only these paths may be touched: `go/internal/slot/`

## Objective
On deadline expiry with an incomplete slot, emit an alert naming the unmet expectation.

## Acceptance criteria
- [ ] Alert names the expectation_id and the missing side
- [ ] Fires once per slot, not per poll
- [ ] Slot moves to MISSING and stops accepting

## Validation
```
make check
```

## Reference
FR-35 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
