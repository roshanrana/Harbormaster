# T-033 — Full slot state machine

**Milestone:** M4  **Depends on:** T-012, T-025  **Status:** `pending`

## Scope
Only these paths may be touched: `go/internal/slot/`

## Objective
Complete the state machine with the T+/-2 late window, per-client overrides and deadline tracking.

## Acceptance criteria
- [ ] Arrival within +/-2 business days binds to the correct historical slot (FR-14, FR-15)
- [ ] Deadline computed on the client calendar, not naive dates
- [ ] Late window overridable per client
- [ ] State transitions exhaustively unit-tested including illegal transitions

## Validation
```
make check
```

## Reference
ADR-010, 03-lld.md §5.5 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
