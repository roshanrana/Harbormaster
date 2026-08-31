# T-036 — Multi-date split

**Milestone:** M4  **Depends on:** T-027  **Status:** `pending`

## Scope
Only these paths may be touched: `python/src/inspector/`

## Objective
A file spanning several value dates splits into per-date sub-batches, each dispatched independently.

## Acceptance criteria
- [ ] sub_batch_index and sub_batch_total populated
- [ ] Each sub-batch writes its own Parquet and its own classified message
- [ ] Row counts across sub-batches sum to the source row count

## Validation
```
make check
```

## Reference
FR-16 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
