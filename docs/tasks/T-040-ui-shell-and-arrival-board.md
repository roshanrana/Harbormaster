# T-040 — UI shell and arrival board

**Milestone:** M6  **Depends on:** T-039  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `go/web/`

## Objective
Server-rendered board with bespoke CSS and vendored HTMX. No Node, no CDN, fully offline.

## Acceptance criteria
- [x] Board lists arrivals with client, domain, resolved value date, confidence, disposition
- [x] Live updates via HTMX SSE swap
- [x] Renders correctly with no network access
- [x] Visual design is deliberate, not default browser styling

## Validation
```
make up && open the board
```

## Reference
ADR-012 — read only what the criteria above require.

## Handoff notes
Server-rendered board with hand-written CSS and vendored HTMX. No Node, no CDN, no build step; renders with no network access. Cool chart-paper palette, serif headings against a tabular-numeral sans for data, hairline rules instead of card shadows.
