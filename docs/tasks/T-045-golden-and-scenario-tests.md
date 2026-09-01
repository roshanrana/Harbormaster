# T-045 — Golden and scenario tests

**Milestone:** M7  **Depends on:** T-044, T-032, T-034  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `tests/`

## Objective
Snapshot tests per fixture plus one named integration test per adversarial scenario.

## Acceptance criteria
- [x] Every fixture has an expected classification and expected Parquet
- [x] Twelve named scenario tests, each asserting the specific behaviour
- [x] Correctness targets NFR-4, NFR-5, NFR-7 measured and reported
- [x] Suite runs offline against the fake adjudicator

## Validation
```
make check && make test-scenarios
```

## Reference
01-requirements.md §8, NFR-4..7 — read only what the criteria above require.

## Handoff notes
17 scenario tests over the twelve adversarial fixtures, each named for the case it covers, plus aggregate assertions for NFR-4, NFR-5, NFR-6 and NFR-7 and a reproducibility check on the corpus generator.
