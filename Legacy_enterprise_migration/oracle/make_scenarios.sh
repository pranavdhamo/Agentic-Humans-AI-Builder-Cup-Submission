#!/usr/bin/env bash
# Regenerate every test scenario and capture its golden output from the REAL COBOL (GnuCOBOL).
# Run from anywhere. Needs: cobc (GnuCOBOL 3.2), python3, and a CardDemo checkout (see run_oracle.sh).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
python3 "$HERE/gen_edge_cases.py"
python3 "$HERE/gen_interest_cases.py"
python3 "$HERE/gen_state_cases.py"

echo "== sample (CardDemo's own data): POSTTRAN then INTCALC"
bash "$HERE/run_oracle.sh" 2>&1 | grep -v "^ld:"

echo "== edge: 122 targeted POSTTRAN transactions"
SCENARIO=edge DALYTRAN_SRC="$HERE/scenarios/edge/DALYTRAN.input" bash "$HERE/run_oracle.sh" 2>&1 | grep -v "^ld:" | head -1

echo "== hidden-state: category-record filler inherited from the last read"
SCENARIO=hidden-state DALYTRAN_SRC="$HERE/scenarios/hidden-state/DALYTRAN.input" STATE_DIR="$HERE/scenarios/hidden-state/state" \
  STAGES=posttran bash "$HERE/run_oracle.sh" 2>&1 | grep -v "^ld:" | head -1

for s in interest-edge interest-abend-account interest-abend-xref interest-abend-rate; do
  echo "== $s: custom initial state, POSTTRAN (empty day) then INTCALC"
  SCENARIO=$s DALYTRAN_SRC="$HERE/scenarios/$s/DALYTRAN.input" STATE_DIR="$HERE/scenarios/$s/state" \
    STAGES="posttran intcalc" bash "$HERE/run_oracle.sh" 2>&1 | grep -v "^ld:" | head -2
done
