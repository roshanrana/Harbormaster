#!/usr/bin/env bash
#
# Drives the adversarial corpus through a running stack, one case at a time,
# narrating what should happen so a viewer can follow along on the board.
#
# Deliberately paced rather than dumping every file at once: the point is to
# watch each hard case being handled, not to prove throughput.
set -euo pipefail

BOARD="${HM_BOARD_URL:-http://localhost:8080}"
LANDING="${HM_LANDING_DIR:-./data/landing}"
STAGE="${HM_DEMO_STAGE:-./data/demo-corpus}"
PAUSE="${HM_DEMO_PAUSE:-6}"

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
dim()  { printf '\033[2m%s\033[0m\n' "$1"; }

step() {
  local title="$1" explanation="$2"; shift 2
  echo
  bold "── $title"
  dim  "   $explanation"
  for f in "$@"; do
    cp "$f" "$LANDING/"
    dim  "   dropped $(basename "$f")"
  done
  sleep "$PAUSE"
}

if ! curl -sf "$BOARD/readyz" >/dev/null; then
  echo "No stack at $BOARD. Run 'make up' first." >&2
  exit 1
fi

mkdir -p "$LANDING"
rm -rf "$STAGE"
bold "Generating the reference corpus"
(cd python && uv run python -c "
from pathlib import Path
from corpus.scenarios import ScenarioBuilder
for s in ScenarioBuilder(Path('../$STAGE')).build_all():
    print(f'  {s.name}')
")

echo
bold "Harbormaster demonstration"
dim  "Open $BOARD and watch the arrivals board as each case lands."
sleep 3

step "1. An ordinary day" \
     "A trade file and its matching ledger extract. Both sides present, so a berth assignment is issued." \
     "$STAGE/01_late_arrival/GL_CLNT004_TRADE_20260828.csv"

step "2. The late file" \
     "Named for the 31st, containing the 28th's business. Harbormaster reads the contents, not the name, and flags the disagreement." \
     "$STAGE/01_late_arrival/MCP_TRD_20260831.csv"

step "3. Four price columns" \
     "An ICE extract with traded, settlement, mark and prior-settle prices. Only two have canonical meaning; the rest are left unassigned rather than guessed." \
     "$STAGE/07_four_prices/ICE_TRD_20260828.csv"

step "4. A column called only 'Price'" \
     "No header vocabulary can separate these. Structure can: a settlement price repeats per instrument, a trade price varies per execution." \
     "$STAGE/08_bare_price/MCP_TRD_20260828.csv"

step "5. A file spanning three value dates" \
     "Split into three sub-batches, each routed to its own reconciliation." \
     "$STAGE/06_multi_date/MCP_TRD_20260831.csv"

step "6. The same file again" \
     "Byte-identical content. Suppressed as a duplicate, and the suppression is recorded rather than silent." \
     "$STAGE/03_exact_duplicate/MCP_TRD_20260828.csv"

step "7. A custody workbook" \
     "Cover sheet, title banner, merged headers and a totals row that is not a holding." \
     "$STAGE/11_awkward_workbook/HF_Custody_Positions_28Aug2026.xlsx"

step "8. A file nobody can identify" \
     "No filename pattern matches and no known account appears. Held for review with a reason that names what could not be decided." \
     "$STAGE/10_unattributable/export_final.csv"

echo
bold "── Where to look now"
dim  "   $BOARD              the arrivals board, with date disagreements flagged"
dim  "   $BOARD/quarantine   the file waiting for a human decision"
dim  "   $BOARD/slots        reconciliation slots and their late windows"
dim  "   Open any arrival to see, column by column, which tier decided it and why."
echo
dim  "   Then run: make verify-audit"
