# T-041 — Arrival detail view

**Milestone:** M6  **Depends on:** T-040  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `go/web/`

## Objective
Per-arrival page showing the value-date reasoning, the confidence breakdown and every field mapping with its tier and evidence.

## Acceptance criteria
- [x] Each mapped field shows source name, canonical name, tier and evidence
- [x] Tier is visually distinguishable at a glance
- [x] Date disagreement shown prominently when flagged
- [x] Account numbers masked, names shown

## Validation
```
make up
```

## Reference
FR-24, ADR-011 — read only what the criteria above require.

## Handoff notes
Arrival detail showing the value-date reasoning beside the per-column provenance table: source column, canonical field, deciding tier as a colour-coded badge, confidence bar and the recorded evidence string. Unresolved columns are shown rather than hidden. Date disagreement gets the loudest treatment in the interface.
