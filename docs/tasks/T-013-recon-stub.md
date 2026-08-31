# T-013 — Recon stub

**Milestone:** M0  **Depends on:** T-008  **Status:** `pending`

## Scope
Only these paths may be touched: `python/src/reconstub/`

## Objective
Consume BerthAssigned, load both Parquet sides, emit a deliberately naive break report to disk and log.

## Acceptance criteria
- [ ] Reads both sides by URI from the assignment
- [ ] Writes a break report naming the client, domain and value date
- [ ] Contains no intelligence whatsoever; that is the point

## Validation
```
make check
```

## Reference
01-requirements.md §2 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
