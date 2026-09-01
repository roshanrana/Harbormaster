# T-017 — JSON queue ingress

**Milestone:** M1  **Depends on:** T-015  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `go/internal/ingress/`

## Objective
Second ingress path: consume JSON payloads from an upstream queue and emit ArrivalRaw with ingress=QUEUE.

## Acceptance criteria
- [x] Queue payload stored to the object store and hashed identically to a file
- [x] Dedupe applies across both ingress paths
- [x] Malformed payload dead-lettered, not crashed on

## Validation
```
make check
```

## Reference
FR-3 — read only what the criteria above require.

## Handoff notes
JSON queue ingress reusing the same processor path as a landed file, so dedupe, audit and classification behave identically for both routes. Payload hashed like a file, so a redelivery after consumer restart is caught by content rather than by any broker guarantee. Malformed payloads skipped, not retried forever. Message ids sanitised against path traversal. 6 tests.
