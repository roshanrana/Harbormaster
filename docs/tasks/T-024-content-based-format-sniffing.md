# T-024 — Content-based format sniffing

**Milestone:** M2  **Depends on:** T-019..T-023  **Status:** `pending`

## Scope
Only these paths may be touched: `python/src/inspector/sniff.py`

## Objective
Decide format from content, never extension. Each parser reports a sniff confidence; highest wins.

## Acceptance criteria
- [ ] A CSV named .txt is detected as CSV
- [ ] A FIXML file named .xml is detected as FIXML, not generic XML
- [ ] An xlsx renamed .csv is detected as EXCEL by magic bytes
- [ ] Ambiguity below threshold routes to quarantine, not a guess

## Validation
```
make check
```

## Reference
FR-17 — read only what the criteria above require.

## Handoff notes
_Filled in on completion. Max 10 lines._
