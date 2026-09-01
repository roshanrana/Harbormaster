# T-042 — Quarantine review and slot board

**Milestone:** M6  **Depends on:** T-040, T-038  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `go/web/`

## Objective
Review screen with approve, correct and reject actions, plus a slot board showing open, partial, assigned and missing.

## Acceptance criteria
- [x] Reviewer can correct client or value date inline and approve
- [x] Action publishes review.decisions and updates the board
- [x] Slot board shows the late window remaining per open slot

## Validation
```
make up
```

## Reference
FR-31, FR-42 — read only what the criteria above require.

## Handoff notes
Quarantine review form posting a named decision, plus a slot board showing state, both sides and the remaining late window, with unmet expectations called out above it.
