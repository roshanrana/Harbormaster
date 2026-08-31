# T-014 — M0 end-to-end test

**Milestone:** M0  **Depends on:** T-010..T-013  **Status:** `pending`

## Scope
Only these paths may be touched: `tests/integration/`

## Objective
Drive the full Compose stack: drop one CSV, assert a break report appears with the right client and value date.

## Acceptance criteria
- [ ] Test starts the stack, seeds one file, polls for the report, tears down
- [ ] Fails loudly if any service is unhealthy
- [ ] Runs in under two minutes

## Validation
```
make test-e2e
```

## Reference
04-execution-plan.md §5 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
