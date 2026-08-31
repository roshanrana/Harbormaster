# T-029 — Tier 2 local matching

**Milestone:** M3  **Depends on:** T-028  **Status:** `pending`

## Scope
Only these paths may be touched: `python/src/inspector/mapping/`

## Objective
Rapidfuzz token-set scoring plus fastembed MiniLM cosine similarity against canonical field descriptions, with a fuzzy-only degraded mode.

## Acceptance criteria
- [ ] Escalation only for headers Tier 1 missed
- [ ] Combined score thresholded; below threshold escalates rather than guessing
- [ ] Model absent falls back to fuzzy-only and records the degradation
- [ ] Evidence string records the matched candidate and score

## Validation
```
make check
```

## Reference
ADR-013, ADR-004 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
