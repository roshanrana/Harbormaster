# T-039 — Control plane read models and API

**Milestone:** M5  **Depends on:** T-037  **Status:** `pending`

## Scope
Only these paths may be touched: `go/cmd/controlplane/, go/internal/web/`

## Objective
Project topics into Postgres read models and serve the LLD §7 API including the SSE stream.

## Acceptance criteria
- [ ] All eight endpoints implemented per LLD §7
- [ ] Projection is idempotent under replay
- [ ] SSE delivers board deltas without polling
- [ ] Masking applied on the way out

## Validation
```
make check
```

## Reference
03-lld.md §7 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
