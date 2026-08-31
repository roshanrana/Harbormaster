# T-040 — UI shell and arrival board

**Milestone:** M6  **Depends on:** T-039  **Status:** `pending`

## Scope
Only these paths may be touched: `go/web/`

## Objective
Server-rendered board with bespoke CSS and vendored HTMX. No Node, no CDN, fully offline.

## Acceptance criteria
- [ ] Board lists arrivals with client, domain, resolved value date, confidence, disposition
- [ ] Live updates via HTMX SSE swap
- [ ] Renders correctly with no network access
- [ ] Visual design is deliberate, not default browser styling

## Validation
```
make up && open the board
```

## Reference
ADR-012 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
