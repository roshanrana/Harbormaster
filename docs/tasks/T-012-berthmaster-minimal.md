# T-012 — Berthmaster minimal

**Milestone:** M0  **Depends on:** T-007, T-008  **Status:** `pending`

## Scope
Only these paths may be touched: `go/cmd/berthmaster/, go/internal/slot/`

## Objective
Open a slot on first arrival, move to PARTIAL, emit BerthAssigned when both sides present. No late window or supersession yet.

## Acceptance criteria
- [ ] Slot key is (client, domain, value_date)
- [ ] State transition and audit write happen in one transaction
- [ ] BerthAssigned published exactly once per completed slot

## Validation
```
make check
```

## Reference
03-lld.md §5.5, §2.6 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
