# T-026 — Client attribution

**Milestone:** M3  **Depends on:** T-025  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `python/src/inspector/attribution.py`

## Objective
Identify the owning client from filename patterns, embedded account identifiers and source hints, with a calibrated confidence.

## Acceptance criteria
- [x] Filename regex hints from client config applied
- [x] Account IDs found in content validated against the registry
- [x] Conflicting evidence lowers confidence rather than picking arbitrarily
- [x] Unattributable file scores below the quarantine threshold

## Validation
```
make check
```

## Reference
FR-18, FR-19 — read only what the criteria above require.

## Handoff notes
Attribution from filename patterns, registry-validated account identifiers and venue hints. Agreement raises confidence to 0.99, disagreement drops it to 0.45 and flags a conflict. Accounts from two clients resolve to nobody rather than a majority vote. 11 tests.
