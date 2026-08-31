# T-026 — Client attribution

**Milestone:** M3  **Depends on:** T-025  **Status:** `pending`

## Scope
Only these paths may be touched: `python/src/inspector/attribution.py`

## Objective
Identify the owning client from filename patterns, embedded account identifiers and source hints, with a calibrated confidence.

## Acceptance criteria
- [ ] Filename regex hints from client config applied
- [ ] Account IDs found in content validated against the registry
- [ ] Conflicting evidence lowers confidence rather than picking arbitrarily
- [ ] Unattributable file scores below the quarantine threshold

## Validation
```
make check
```

## Reference
FR-18, FR-19 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
