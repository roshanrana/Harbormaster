# T-016 — Dedupe and suppression

**Milestone:** M1  **Depends on:** T-015, T-007  **Status:** `pending`

## Scope
Only these paths may be touched: `go/internal/arrival/, go/internal/store/`

## Objective
Content-hash dedupe store. Identical content under a different filename is a redelivery, not a new arrival.

## Acceptance criteria
- [ ] Exact duplicate suppressed, no ArrivalRaw published
- [ ] Suppression written to the audit topic referencing the original arrival_id
- [ ] Different filename, same content still suppressed (FR-7)
- [ ] Board can show a seen-count rather than silently discarding

## Validation
```
make check
```

## Reference
FR-6, FR-7, HLD §5.5 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
