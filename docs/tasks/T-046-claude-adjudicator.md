# T-046 — Claude adjudicator

**Milestone:** M8  **Depends on:** T-030  **Status:** `pending`

## Scope
Only these paths may be touched: `python/src/inspector/mapping/tier3_llm.py`

## Objective
Implement the live adjudicator behind the frozen interface: structured output, prompt caching, bounded retry, cost counter.

## Acceptance criteria
- [ ] Returns a mapping validated against the canonical schema before use
- [ ] Malformed or invalid output falls back to local tiers and marks UNRESOLVED
- [ ] Prompt cache reuses the client context block across calls
- [ ] Per-call token and cost counters logged

## Validation
```
make check
```

## Reference
R-2, ADR-004, C-3 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
