# T-014 — M0 end-to-end test

**Milestone:** M0  **Depends on:** T-010..T-013  **Status:** `done` — validate-on-host

## Scope
Only these paths may be touched: `tests/integration/`

## Objective
Drive the full Compose stack: drop one CSV, assert a break report appears with the right client and value date.

## Acceptance criteria
- [x] Test starts the stack, seeds one file, polls for the report, tears down
- [x] Fails loudly if any service is unhealthy
- [x] Runs in under two minutes

## Validation
```
make test-e2e
```

## Reference
04-execution-plan.md §5 — read only what the criteria above require.

## Handoff notes
End-to-end test written against the running stack: seeds the adversarial corpus, asserts the late file resolves to 2026-08-28 through the real broker and both languages, a berth assignment is issued, the recon stub writes a break report, and the unattributable file reaches the review queue. Skipped automatically when no stack is reachable. validate-on-host per ADR-018.
