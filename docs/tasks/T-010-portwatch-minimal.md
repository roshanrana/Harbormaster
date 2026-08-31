# T-010 — Portwatch minimal

**Milestone:** M0  **Depends on:** T-008  **Status:** `pending`

## Scope
Only these paths may be touched: `go/cmd/portwatch/, go/internal/ingress/`

## Objective
Watch a directory, hash new files, store the raw payload, publish ArrivalRaw. No stability logic yet.

## Acceptance criteria
- [ ] A file dropped into the landing dir produces exactly one ArrivalRaw
- [ ] content_sha256 matches sha256sum of the file
- [ ] Raw payload readable back from the object store by URI

## Validation
```
make check && make test-e2e-portwatch
```

## Reference
03-lld.md §2.2, §5.1 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
