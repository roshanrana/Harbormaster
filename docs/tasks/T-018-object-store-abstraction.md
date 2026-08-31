# T-018 — Object store abstraction

**Milestone:** M1  **Depends on:** T-002  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `go/internal/store/objectstore/`

## Objective
ObjectStore interface with an fs adapter (default) and an s3 adapter, implemented and unit-tested but not wired into the demo.

## Acceptance criteria
- [x] Interface covers put, get, stat, uri round-trip
- [x] fs adapter used by default via HM_OBJECT_STORE=fs
- [x] s3 adapter unit-tested against a fake; no MinIO container

## Validation
```
make check
```

## Reference
ADR-015 — read only what the criteria above require.

## Handoff notes
ObjectStore interface, fs adapter default, hash computed during the write. Traversal keys rejected explicitly; a failed write leaves nothing visible. 6 tests.
