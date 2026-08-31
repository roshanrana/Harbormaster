# T-022 — Email text parser

**Milestone:** M2  **Depends on:** T-011  **Status:** `pending`

## Scope
Only these paths may be touched: `python/src/inspector/parsers/`

## Objective
Extract structured records from a free-text email body describing cash or collateral movements.

## Acceptance criteria
- [ ] Amounts, currencies, dates and account references extracted with positions retained
- [ ] Multiple movements in one body produce multiple rows
- [ ] Low extraction confidence propagates rather than being hidden

## Validation
```
make check
```

## Reference
FR-22, corpus case 9 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
