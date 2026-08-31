# T-017 — JSON queue ingress

**Milestone:** M1  **Depends on:** T-015  **Status:** `pending`

## Scope
Only these paths may be touched: `go/internal/ingress/`

## Objective
Second ingress path: consume JSON payloads from an upstream queue and emit ArrivalRaw with ingress=QUEUE.

## Acceptance criteria
- [ ] Queue payload stored to the object store and hashed identically to a file
- [ ] Dedupe applies across both ingress paths
- [ ] Malformed payload dead-lettered, not crashed on

## Validation
```
make check
```

## Reference
FR-3 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
