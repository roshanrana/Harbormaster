# T-024 — Content-based format sniffing

**Milestone:** M2  **Depends on:** T-019..T-023  **Status:** `done` — validated-here

## Scope
Only these paths may be touched: `python/src/inspector/sniff.py`

## Objective
Decide format from content, never extension. Each parser reports a sniff confidence; highest wins.

## Acceptance criteria
- [x] A CSV named .txt is detected as CSV
- [x] A FIXML file named .xml is detected as FIXML, not generic XML
- [x] An xlsx renamed .csv is detected as EXCEL by magic bytes
- [x] Ambiguity below threshold routes to quarantine, not a guess

## Validation
```
make check
```

## Reference
FR-17 — read only what the criteria above require.

## Handoff notes
Content-based format sniffing with per-parser confidence; a CSV named .txt still classifies as CSV. Unrecognised content raises rather than guessing.
