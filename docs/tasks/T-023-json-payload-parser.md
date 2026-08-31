# T-023 — JSON payload parser

**Milestone:** M2  **Depends on:** T-011  **Status:** `pending`

## Scope
Only these paths may be touched: `python/src/inspector/parsers/`

## Objective
Parse queue JSON payloads, including nested and array-of-record shapes.

## Acceptance criteria
- [ ] Array-of-objects and single-object shapes both handled
- [ ] Nested objects flattened to dotted source_field paths
- [ ] Type information preserved into the canonical decimals

## Validation
```
make check
```

## Reference
FR-3 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
