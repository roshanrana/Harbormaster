# T-019 — Excel parser

**Milestone:** M2  **Depends on:** T-011  **Status:** `pending`

## Scope
Only these paths may be touched: `python/src/inspector/parsers/`

## Objective
Parse xlsx to ParsedTable: detect the header row, handle merged cells, skip trailing totals rows, pick the right sheet.

## Acceptance criteria
- [ ] Header detected when preceded by title and blank rows
- [ ] Merged header cells forward-filled correctly
- [ ] A trailing 'Total' row is excluded from row_count
- [ ] Multi-sheet workbook selects the data sheet, not the cover sheet

## Validation
```
make check
```

## Reference
R-4, 03-lld.md §5.2 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
