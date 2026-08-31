# T-018 — Object store abstraction

**Milestone:** M1  **Depends on:** T-002  **Status:** `pending`

## Scope
Only these paths may be touched: `go/internal/store/objectstore/`

## Objective
ObjectStore interface with an fs adapter (default) and an s3 adapter, implemented and unit-tested but not wired into the demo.

## Acceptance criteria
- [ ] Interface covers put, get, stat, uri round-trip
- [ ] fs adapter used by default via HM_OBJECT_STORE=fs
- [ ] s3 adapter unit-tested against a fake; no MinIO container

## Validation
```
make check
```

## Reference
ADR-015 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
