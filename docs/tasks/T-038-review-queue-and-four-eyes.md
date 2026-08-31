# T-038 — Review queue and four-eyes

**Milestone:** M5  **Depends on:** T-037, T-033  **Status:** `pending`

## Scope
Only these paths may be touched: `go/internal/web/, go/internal/slot/`

## Objective
Quarantine queue, decision endpoint, and the review.decisions consumer that releases or rejects an arrival.

## Acceptance criteria
- [ ] No quarantined arrival dispatches without a recorded human decision (FR-32)
- [ ] Reviewer identity stamped on the audit record
- [ ] Corrections can override client, value date or a field mapping
- [ ] An approved correction is promotable into the client dictionary

## Validation
```
make check
```

## Reference
FR-31, FR-32 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
