# T-021 — FIXML parser

**Milestone:** M2  **Depends on:** T-020  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `python/src/inspector/parsers/`

## Objective
FIXML documents to ParsedTable, including repeating groups and standard tag semantics.

## Acceptance criteria
- [x] Execution report elements mapped to rows
- [x] Repeating groups flattened without collision
- [x] Tag names preserved as source_field for provenance
- [x] No FIX session logic; files only

## Validation
```
make check
```

## Reference
FR-22, out-of-scope §7 — read only what the criteria above require.

## Handoff notes
FIXML parser: translates standard FIX tags to dictionary-friendly headers, decodes Side enums, names the security identifier by its IDSrc so ISIN and CUSIP are distinguishable, extracts the customer account from Pty role 24. 5 tests.
