# T-025 — Client registry and calendars

**Milestone:** M3  **Depends on:** T-002  **Status:** `pending`

## Scope
Only these paths may be touched: `go/internal/registry/, config/`

## Objective
Load and validate per-client YAML per LLD §4, plus business calendars. Unknown keys are errors. Hot reload.

## Acceptance criteria
- [ ] Six example client configs across five venues committed
- [ ] Invalid config fails at load with a path pointer to the offending key
- [ ] cuts_per_day honoured (FR-10)
- [ ] Calendars cover weekends and venue holidays

## Validation
```
make check
```

## Reference
03-lld.md §4, FR-33 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
