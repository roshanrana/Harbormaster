# T-011 — Inspector minimal

**Milestone:** M0  **Depends on:** T-008  **Status:** `pending`

## Scope
Only these paths may be touched: `python/src/inspector/`

## Objective
Consume ArrivalRaw, sniff CSV, parse, apply Tier 1 alias mapping only, write canonical Parquet, publish ArrivalClassified.

## Acceptance criteria
- [ ] A well-formed CSV trade file maps at least 10 columns via Tier 1
- [ ] Parquet output matches the LLD §3 schema with decimal types, not floats
- [ ] Every FieldMapping carries a tier and confidence; none are blank

## Validation
```
make check
```

## Reference
03-lld.md §2.3, §3 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
