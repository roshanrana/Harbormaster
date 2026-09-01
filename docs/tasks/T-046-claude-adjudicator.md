# T-046 — Claude adjudicator

**Milestone:** M8  **Depends on:** T-030  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `python/src/inspector/mapping/tier3_llm.py`

## Objective
Implement the live adjudicator behind the frozen interface: structured output, prompt caching, bounded retry, cost counter.

## Acceptance criteria
- [x] Returns a mapping validated against the canonical schema before use
- [x] Malformed or invalid output falls back to local tiers and marks UNRESOLVED
- [x] Prompt cache reuses the client context block across calls
- [x] Per-call token and cost counters logged

## Validation
```
make check
```

## Reference
R-2, ADR-004, C-3 — read only what the criteria above require.

## Handoff notes
ClaudeAdjudicator behind the frozen interface: structured output validated against the canonical schema before use, invented field names discarded, bounded retries with a clean fallback to unresolved, prompt caching on the stable prefix, token and latency accounting. 16 tests against a stub transport, no network.
