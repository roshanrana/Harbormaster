# T-034 — Supersession

**Milestone:** M4  **Depends on:** T-033  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `go/internal/slot/`

## Objective
Correction handling: emit BerthSuperseded then a replacement BerthAssigned, strictly ordered on the same partition.

## Acceptance criteria
- [x] Same client/domain/value_date with a new hash supersedes
- [x] Void always observed before replacement by every consumer
- [x] cuts_per_day distinguishes a correction from a legitimate second cut (FR-10)
- [x] Prior assignment_id carried on the replacement

## Validation
```
make check
```

## Reference
FR-8, FR-9, ADR-005 — read only what the criteria above require.

## Handoff notes
Correction after dispatch carries the prior assignment id; a replacement before dispatch correctly does not supersede.
