# T-021 — FIXML parser

**Milestone:** M2  **Depends on:** T-020  **Status:** `pending`

## Scope
Only these paths may be touched: `python/src/inspector/parsers/`

## Objective
FIXML documents to ParsedTable, including repeating groups and standard tag semantics.

## Acceptance criteria
- [ ] Execution report elements mapped to rows
- [ ] Repeating groups flattened without collision
- [ ] Tag names preserved as source_field for provenance
- [ ] No FIX session logic; files only

## Validation
```
make check
```

## Reference
FR-22, out-of-scope §7 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
