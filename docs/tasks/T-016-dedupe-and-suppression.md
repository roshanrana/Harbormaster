# T-016 — Dedupe and suppression

**Milestone:** M1  **Depends on:** T-015, T-007  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `go/internal/arrival/, go/internal/store/`

## Objective
Content-hash dedupe store. Identical content under a different filename is a redelivery, not a new arrival.

## Acceptance criteria
- [x] Exact duplicate suppressed, no ArrivalRaw published
- [x] Suppression written to the audit topic referencing the original arrival_id
- [x] Different filename, same content still suppressed (FR-7)
- [x] Board can show a seen-count rather than silently discarding

## Validation
```
make check
```

## Reference
FR-6, FR-7, HLD §5.5 — read only what the criteria above require.

## Handoff notes
Content-hash dedupe with three verdicts (NEW, DUPLICATE, REDELIVERY). Suppression is audited rather than silent, because a resending client is an operational signal. Schema constraint arbitrates races, not application code.
