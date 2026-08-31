# T-043 — Corpus generator

**Milestone:** M7  **Depends on:** T-024, T-025  **Status:** `pending`

## Scope
Only these paths may be touched: `corpus/, config/`

## Objective
Deterministic generator producing realistic files across six clients, five venues and all six formats.

## Acceptance criteria
- [ ] Seeded and reproducible; same seed produces identical bytes
- [ ] Venue-specific column vocabulary per source
- [ ] Realistic instrument identifiers, currencies and settlement conventions
- [ ] Includes a matching internal GL extract for each external file

## Validation
```
make seed && make check
```

## Reference
01-requirements.md §8 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
