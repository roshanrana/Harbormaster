# T-045 — Golden and scenario tests

**Milestone:** M7  **Depends on:** T-044, T-032, T-034  **Status:** `pending`

## Scope
Only these paths may be touched: `tests/`

## Objective
Snapshot tests per fixture plus one named integration test per adversarial scenario.

## Acceptance criteria
- [ ] Every fixture has an expected classification and expected Parquet
- [ ] Twelve named scenario tests, each asserting the specific behaviour
- [ ] Correctness targets NFR-4, NFR-5, NFR-7 measured and reported
- [ ] Suite runs offline against the fake adjudicator

## Validation
```
make check && make test-scenarios
```

## Reference
01-requirements.md §8, NFR-4..7 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
