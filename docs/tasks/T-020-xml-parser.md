# T-020 — XML parser

**Milestone:** M2  **Depends on:** T-011  **Status:** `pending`

## Scope
Only these paths may be touched: `python/src/inspector/parsers/`

## Objective
Generic XML to ParsedTable via repeating-element detection and path flattening; source_field is the XPath.

## Acceptance criteria
- [ ] Repeating record element detected without configuration
- [ ] Nested elements flattened to dotted paths
- [ ] Attributes captured alongside elements

## Validation
```
make check
```

## Reference
FR-22 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
