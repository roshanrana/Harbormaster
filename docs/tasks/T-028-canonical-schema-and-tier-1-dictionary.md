# T-028 — Canonical schema and Tier 1 dictionary

**Milestone:** M3  **Depends on:** T-011  **Status:** `pending`

## Scope
Only these paths may be touched: `python/src/inspector/mapping/`

## Objective
Freeze the canonical record and build the alias dictionary covering real venue and custody vocabulary.

## Acceptance criteria
- [ ] Header normalisation strips case, spaces, punctuation and unit suffixes
- [ ] Dictionary covers ICE, CME, CBOE, LSEG, EUREX, NYSE, HKEX and Nasdaq conventions
- [ ] field_overrides from client config take precedence over the global dictionary
- [ ] No canonical field can be assigned twice in one mapping

## Validation
```
make check
```

## Reference
03-lld.md §3, ADR-004 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
