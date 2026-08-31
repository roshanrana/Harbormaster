# T-047 — Live smoke test

**Milestone:** M8  **Depends on:** T-046, T-045  **Status:** `pending`

## Scope
Only these paths may be touched: `tests/live/`

## Objective
Opt-in test hitting the real API, skipped unless ANTHROPIC_API_KEY and HM_LIVE=1 are set.

## Acceptance criteria
- [ ] Skipped by default; make check never calls the network
- [ ] Verifies a genuinely novel header set is mapped correctly
- [ ] Measures the T3 escalation rate against the NFR-8 target of 2 percent

## Validation
```
HM_LIVE=1 make test-live
```

## Reference
NFR-8, C-3 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
