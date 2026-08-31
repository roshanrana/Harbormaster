# T-013 — Recon stub

**Milestone:** M0  **Depends on:** T-008  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `python/src/reconstub/`

## Objective
Consume BerthAssigned, load both Parquet sides, emit a deliberately naive break report to disk and log.

## Acceptance criteria
- [x] Reads both sides by URI from the assignment
- [x] Writes a break report naming the client, domain and value date
- [x] Contains no intelligence whatsoever; that is the point

## Validation
```
make check
```

## Reference
01-requirements.md §2 — read only what the criteria above require.

## Handoff notes
Recon stub joins on account/instrument/trade, compares material fields with a rounding tolerance, writes a JSON break report. Deliberately has no intelligence. 8 tests including that a null settlement price is never treated as zero.
