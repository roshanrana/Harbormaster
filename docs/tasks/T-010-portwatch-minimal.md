# T-010 — Portwatch minimal

**Milestone:** M0  **Depends on:** T-008  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `go/cmd/portwatch/, go/internal/ingress/`

## Objective
Watch a directory, hash new files, store the raw payload, publish ArrivalRaw. No stability logic yet.

## Acceptance criteria
- [x] A file dropped into the landing dir produces exactly one ArrivalRaw
- [x] content_sha256 matches sha256sum of the file
- [x] Raw payload readable back from the object store by URI

## Validation
```
make check && make test-e2e-portwatch
```

## Reference
03-lld.md §2.2, §5.1 — read only what the criteria above require.

## Handoff notes
Portwatch publishes ArrivalRaw with a streaming SHA-256; payload retrievable from the object store by URI. 5 processor tests against real Postgres.
