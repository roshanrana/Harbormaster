# T-031 — Price disambiguation

**Milestone:** M3  **Depends on:** T-028  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `python/src/inspector/mapping/prices.py`

## Objective
All four steps from LLD §5.3: vocabulary, overrides, structural constancy, amount cross-check.

## Acceptance criteria
- [x] A file with four price columns resolves trade and settlement correctly
- [x] A bare column named only 'Price' resolved by structural evidence
- [x] quantity x candidate ~ net_amount used as the tie-break
- [x] Unresolvable ambiguity quarantines rather than guessing (FR-25)

## Validation
```
make check
```

## Reference
03-lld.md §5.3, FR-25, FR-26 — read only what the criteria above require.

## Handoff notes
Four-pass price resolution: vocabulary, preference ranking, structural variation within instrument groups, arithmetic cross-check. Surplus price columns left explicitly unassigned. 18 tests.
