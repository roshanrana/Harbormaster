# T-029 — Tier 2 local matching

**Milestone:** M3  **Depends on:** T-028  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `python/src/inspector/mapping/`

## Objective
Rapidfuzz token-set scoring plus fastembed MiniLM cosine similarity against canonical field descriptions, with a fuzzy-only degraded mode.

## Acceptance criteria
- [x] Escalation only for headers Tier 1 missed
- [x] Combined score thresholded; below threshold escalates rather than guessing
- [x] Model absent falls back to fuzzy-only and records the degradation
- [x] Evidence string records the matched candidate and score

## Validation
```
make check
```

## Reference
ADR-013, ADR-004 — read only what the criteria above require.

## Handoff notes
Tier 2 combines rapidfuzz token-set scoring with optional ONNX embeddings; the two signals fail differently so both run and agreement is treated as corroboration. Confidence capped below alias level so provenance stays meaningful. Degraded mode is recorded in the evidence string, never silent. 5 tests.
