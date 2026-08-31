# T-012 — Berthmaster minimal

**Milestone:** M0  **Depends on:** T-007, T-008  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `go/cmd/berthmaster/, go/internal/slot/`

## Objective
Open a slot on first arrival, move to PARTIAL, emit BerthAssigned when both sides present. No late window or supersession yet.

## Acceptance criteria
- [x] Slot key is (client, domain, value_date)
- [x] State transition and audit write happen in one transaction
- [x] BerthAssigned published exactly once per completed slot

## Validation
```
make check
```

## Reference
03-lld.md §5.5, §2.6 — read only what the criteria above require.

## Handoff notes
Slot state machine with OPEN/PARTIAL/ASSIGNED/SUPERSEDED/MISSING, plus the SQL store. Berthmaster binary consumes classified arrivals, publishes voids before replacements on the slot partition key, and sweeps for overdue slots on its own timer. 18 tests.
