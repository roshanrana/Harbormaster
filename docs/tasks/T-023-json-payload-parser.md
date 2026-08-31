# T-023 — JSON payload parser

**Milestone:** M2  **Depends on:** T-011  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `python/src/inspector/parsers/`

## Objective
Parse queue JSON payloads, including nested and array-of-record shapes.

## Acceptance criteria
- [x] Array-of-objects and single-object shapes both handled
- [x] Nested objects flattened to dotted source_field paths
- [x] Type information preserved into the canonical decimals

## Validation
```
make check
```

## Reference
FR-3 — read only what the criteria above require.

## Handoff notes
JSON parser: locates records under a named key or the longest object array, keeps scalar envelope fields on every row, flattens nesting to dotted paths, bounded depth so a pathological payload cannot block a partition. 6 tests.
