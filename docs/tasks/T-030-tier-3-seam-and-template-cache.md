# T-030 — Tier 3 seam and template cache

**Milestone:** M3  **Depends on:** T-029  **Status:** `pending`

## Scope
Only these paths may be touched: `python/src/inspector/mapping/`

## Objective
MappingAdjudicator protocol, DeterministicFake, and a template-fingerprint cache in Postgres. No live API calls in this task.

## Acceptance criteria
- [ ] Fingerprint is an ordered hash of the header set plus client
- [ ] Second file with the same layout costs zero adjudications
- [ ] Fake is bound by default so the whole suite runs offline (NFR-12)
- [ ] Confirmed decisions promotable into client field_overrides (FR-28)

## Validation
```
make check
```

## Reference
03-lld.md §5.2, ADR-004 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
