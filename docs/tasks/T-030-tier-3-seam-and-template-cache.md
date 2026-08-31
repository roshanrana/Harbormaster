# T-030 — Tier 3 seam and template cache

**Milestone:** M3  **Depends on:** T-029  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `python/src/inspector/mapping/`

## Objective
MappingAdjudicator protocol, DeterministicFake, and a template-fingerprint cache in Postgres. No live API calls in this task.

## Acceptance criteria
- [x] Fingerprint is an ordered hash of the header set plus client
- [x] Second file with the same layout costs zero adjudications
- [x] Fake is bound by default so the whole suite runs offline (NFR-12)
- [x] Confirmed decisions promotable into client field_overrides (FR-28)

## Validation
```
make check
```

## Reference
03-lld.md §5.2, ADR-004 — read only what the criteria above require.

## Handoff notes
MappingAdjudicator protocol with a DeterministicFake bound by default, so the whole suite runs offline with no API key. Template fingerprint cache with in-memory and Postgres implementations; the durable one is shared so model cost does not scale with consumer count. Promotion into client config requires a reviewer. 15 tests plus 5 against real Postgres.
