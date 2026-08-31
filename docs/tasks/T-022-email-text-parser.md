# T-022 — Email text parser

**Milestone:** M2  **Depends on:** T-011  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `python/src/inspector/parsers/`

## Objective
Extract structured records from a free-text email body describing cash or collateral movements.

## Acceptance criteria
- [x] Amounts, currencies, dates and account references extracted with positions retained
- [x] Multiple movements in one body produce multiple rows
- [x] Low extraction confidence propagates rather than being hidden

## Validation
```
make check
```

## Reference
FR-22, corpus case 9 — read only what the criteria above require.

## Handoff notes
Email-text parser: line-oriented extraction requiring both amount and currency, signed by direction, per-line extraction confidence carried out as a column so a thinly-understood advice quarantines. Near-miss lines are counted and surfaced. 7 tests.
