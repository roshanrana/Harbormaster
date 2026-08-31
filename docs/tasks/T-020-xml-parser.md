# T-020 — XML parser

**Milestone:** M2  **Depends on:** T-011  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `python/src/inspector/parsers/`

## Objective
Generic XML to ParsedTable via repeating-element detection and path flattening; source_field is the XPath.

## Acceptance criteria
- [x] Repeating record element detected without configuration
- [x] Nested elements flattened to dotted paths
- [x] Attributes captured alongside elements

## Validation
```
make check
```

## Reference
FR-22 — read only what the criteria above require.

## Handoff notes
XML parser: finds the repeating record element by content weight rather than assuming root children, flattens to dotted paths with attributes prefixed, suffixes repeating groups so a two-leg trade keeps both legs. Defers to FIXML. 6 tests.
