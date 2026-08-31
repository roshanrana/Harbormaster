# T-044 — Adversarial fixtures

**Milestone:** M7  **Depends on:** T-043  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `corpus/`

## Objective
The twelve named cases from requirements §8, each an explicit, documented fixture.

## Acceptance criteria
- [x] All twelve present and individually named
- [x] Each fixture documents what it is designed to break
- [x] Includes the late arrival, the date disagreement, the correction, the multi-date file, the four-price record, the bare Price header, the email blob and the unattributable file

## Validation
```
make check
```

## Reference
01-requirements.md §8 — read only what the criteria above require.

## Handoff notes
All twelve adversarial fixtures from requirements section 8, each carrying what it is designed to break and what is expected.
