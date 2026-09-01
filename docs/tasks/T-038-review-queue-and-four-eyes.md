# T-038 — Review queue and four-eyes

**Milestone:** M5  **Depends on:** T-037, T-033  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `go/internal/web/, go/internal/slot/`

## Objective
Quarantine queue, decision endpoint, and the review.decisions consumer that releases or rejects an arrival.

## Acceptance criteria
- [x] No quarantined arrival dispatches without a recorded human decision (FR-32)
- [x] Reviewer identity stamped on the audit record
- [x] Corrections can override client, value date or a field mapping
- [x] An approved correction is promotable into the client dictionary

## Validation
```
make check
```

## Reference
FR-31, FR-32 — read only what the criteria above require.

## Handoff notes
Four-eyes review enforced by a primary key rather than a racy check: a second reviewer gets 409. A CORRECT carrying no corrections is refused, an anonymous decision is refused, and a reviewed item leaves the queue so two people cannot work it. Decision is persisted before it is published, so a publish failure cannot release a file with no record of who released it.
