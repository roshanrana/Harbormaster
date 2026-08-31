# T-019 — Excel parser

**Milestone:** M2  **Depends on:** T-011  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `python/src/inspector/parsers/`

## Objective
Parse xlsx to ParsedTable: detect the header row, handle merged cells, skip trailing totals rows, pick the right sheet.

## Acceptance criteria
- [x] Header detected when preceded by title and blank rows
- [x] Merged header cells forward-filled correctly
- [x] A trailing 'Total' row is excluded from row_count
- [x] Multi-sheet workbook selects the data sheet, not the cover sheet

## Validation
```
make check
```

## Reference
R-4, 03-lld.md §5.2 — read only what the criteria above require.

## Handoff notes
Excel parser: scores sheets so a cover sheet loses to the data sheet, finds the header below a title banner, forward-fills merged header cells, excludes trailing totals. Magic-byte sniffing. Non-zip .xlsx rejects cleanly as MALFORMED. 8 tests.
