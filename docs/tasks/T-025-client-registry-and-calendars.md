# T-025 — Client registry and calendars

**Milestone:** M3  **Depends on:** T-002  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `go/internal/registry/, config/`

## Objective
Load and validate per-client YAML per LLD §4, plus business calendars. Unknown keys are errors. Hot reload.

## Acceptance criteria
- [x] Six example client configs across five venues committed
- [x] Invalid config fails at load with a path pointer to the offending key
- [x] cuts_per_day honoured (FR-10)
- [x] Calendars cover weekends and venue holidays

## Validation
```
make check
```

## Reference
03-lld.md §4, FR-33 — read only what the criteria above require.

## Handoff notes
Six client configs across five venues plus four market calendars. Strict YAML loading rejects unknown keys and names the offending file and path. Business-day arithmetic lives in the registry so late windows, deadlines and value-date rolling share one implementation. 15 tests, including that UK and US calendars genuinely differ on 2026-08-31.
