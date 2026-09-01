# T-039 — Control plane read models and API

**Milestone:** M5  **Depends on:** T-037  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `go/cmd/controlplane/, go/internal/web/`

## Objective
Project topics into Postgres read models and serve the LLD §7 API including the SSE stream.

## Acceptance criteria
- [x] All eight endpoints implemented per LLD §7
- [x] Projection is idempotent under replay
- [x] SSE delivers board deltas without polling
- [x] Masking applied on the way out

## Validation
```
make check
```

## Reference
03-lld.md §7 — read only what the criteria above require.

## Handoff notes
Read-model projector consuming five topics into Postgres, idempotent by producer-owned identifiers so the board never double-counts under at-least-once delivery. Nine REST endpoints plus an SSE stream whose hub drops slow subscribers rather than blocking the projector. Readiness checks the store, not just the process. 20 tests against real Postgres.
