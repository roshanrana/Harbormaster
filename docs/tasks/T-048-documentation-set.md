# T-048 — Documentation set

**Milestone:** M9  **Depends on:** T-045  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `docs/, README.md`

## Objective
README with the architecture narrative, a runbook, and a rationale document explaining why each significant choice was made.

## Acceptance criteria
- [x] README explains the problem before the solution
- [x] Every non-obvious tool choice traceable to an ADR
- [x] Runbook covers start, seed, demo, verify, teardown and common failures
- [x] Diagrams match the code as built, not as designed

## Validation
```
make check
```

## Reference
C-6 — read only what the criteria above require.

## Handoff notes
README leading with the problem before the solution, runbook covering start/seed/demo/verify/teardown plus seven named failure modes, and every non-obvious choice traceable to one of twenty ADRs.
