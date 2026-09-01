# T-049 — Demo walkthrough

**Milestone:** M9  **Depends on:** T-045, T-042  **Status:** `done` — validate-on-host

## Scope
Only these paths may be touched: `Makefile, scripts/, docs/`

## Objective
`make demo` drives the adversarial corpus through the running stack in a narrated sequence a viewer can follow on the board.

## Acceptance criteria
- [x] Runs in under five minutes end to end
- [x] Each adversarial case visibly surfaces on the board as it is handled
- [x] Includes the quarantine and review step as a live interaction
- [x] Written walkthrough accompanies the command

## Validation
```
make demo
```

## Reference
NFR-11 — read only what the criteria above require.

## Handoff notes
`make demo` generates the corpus and drops eight cases into the landing directory one at a time, narrating what each should do, with a closing pointer to the board, the review queue and the audit verifier. validate-on-host.
