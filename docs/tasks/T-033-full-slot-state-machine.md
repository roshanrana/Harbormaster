# T-033 — Full slot state machine

**Milestone:** M4  **Depends on:** T-012, T-025  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `go/internal/slot/`

## Objective
Complete the state machine with the T+/-2 late window, per-client overrides and deadline tracking.

## Acceptance criteria
- [x] Arrival within +/-2 business days binds to the correct historical slot (FR-14, FR-15)
- [x] Deadline computed on the client calendar, not naive dates
- [x] Late window overridable per client
- [x] State transitions exhaustively unit-tested including illegal transitions

## Validation
```
make check
```

## Reference
ADR-010, 03-lld.md §5.5 — read only what the criteria above require.

## Handoff notes
T+/-2 window measured in business days on the client calendar, per-client override honoured. Late file binds to its historical slot and does not leak into today.
