# T-004 — Protobuf contracts and codegen

**Milestone:** G  **Depends on:** T-002, T-003  **Status:** `pending`

## Scope
Only these paths may be touched: `proto/, buf.*, go/gen/, python/src/hmv1/`

## Objective
Author every message in LLD §2 as proto3, configure buf, generate Go and Python types, and add a codegen-freshness check that fails if generated code is stale.

## Acceptance criteria
- [ ] Every message and enum in LLD §2 present with the exact field numbers
- [ ] buf lint and buf breaking pass
- [ ] Regenerating produces no diff; a deliberate stale edit fails the check
- [ ] Round-trip test: Go marshals protojson, Python unmarshals, fields equal

## Validation
```
buf lint && buf generate && git diff --exit-code
```

## Reference
03-lld.md §2 (frozen) — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
