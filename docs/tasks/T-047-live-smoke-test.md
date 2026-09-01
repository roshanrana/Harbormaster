# T-047 — Live smoke test

**Milestone:** M8  **Depends on:** T-046, T-045  **Status:** `done` — validate-on-host

## Scope
Only these paths may be touched: `tests/live/`

## Objective
Opt-in test hitting the real API, skipped unless ANTHROPIC_API_KEY and HM_LIVE=1 are set.

## Acceptance criteria
- [x] Skipped by default; make check never calls the network
- [x] Verifies a genuinely novel header set is mapped correctly
- [x] Measures the T3 escalation rate against the NFR-8 target of 2 percent

## Validation
```
HM_LIVE=1 make test-live
```

## Reference
NFR-8, C-3 — read only what the criteria above require.

## Handoff notes
Opt-in live test requiring both HM_LIVE=1 and ANTHROPIC_API_KEY. Verifies genuinely novel headers map correctly from sample values, no canonical field is used twice, an unmappable column is declined rather than invented, and cost is recorded. validate-on-host.
