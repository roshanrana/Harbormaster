# T-043 — Corpus generator

**Milestone:** M7  **Depends on:** T-024, T-025  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `corpus/, config/`

## Objective
Deterministic generator producing realistic files across six clients, five venues and all six formats.

## Acceptance criteria
- [x] Seeded and reproducible; same seed produces identical bytes
- [x] Venue-specific column vocabulary per source
- [x] Realistic instrument identifiers, currencies and settlement conventions
- [x] Includes a matching internal GL extract for each external file

## Validation
```
make seed && make check
```

## Reference
01-requirements.md §8 — read only what the criteria above require.

## Handoff notes
Deterministic seeded corpus generator with eight venue vocabularies (CME, ICE, EUREX, LSEG, HKEX, NASDAQ, CBOE, NYSE), eleven instruments across five currencies, and writers for delimited, Excel, XML, FIXML, JSON and email. Settlement prices repeat per instrument so the structural price signal is genuine, not manufactured. Matching GL extract per file.
