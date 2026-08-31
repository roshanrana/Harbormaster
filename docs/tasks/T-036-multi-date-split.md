# T-036 — Multi-date split

**Milestone:** M4  **Depends on:** T-027  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `python/src/inspector/`

## Objective
A file spanning several value dates splits into per-date sub-batches, each dispatched independently.

## Acceptance criteria
- [x] sub_batch_index and sub_batch_total populated
- [x] Each sub-batch writes its own Parquet and its own classified message
- [x] Row counts across sub-batches sum to the source row count

## Validation
```
make check
```

## Reference
FR-16 — read only what the criteria above require.

## Handoff notes
Multi-date files split into per-date sub-batches with index and total carried on the wire; row counts sum to the source.
