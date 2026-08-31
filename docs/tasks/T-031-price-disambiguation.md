# T-031 — Price disambiguation

**Milestone:** M3  **Depends on:** T-028  **Status:** `pending`

## Scope
Only these paths may be touched: `python/src/inspector/mapping/prices.py`

## Objective
All four steps from LLD §5.3: vocabulary, overrides, structural constancy, amount cross-check.

## Acceptance criteria
- [ ] A file with four price columns resolves trade and settlement correctly
- [ ] A bare column named only 'Price' resolved by structural evidence
- [ ] quantity x candidate ~ net_amount used as the tie-break
- [ ] Unresolvable ambiguity quarantines rather than guessing (FR-25)

## Validation
```
make check
```

## Reference
03-lld.md §5.3, FR-25, FR-26 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
