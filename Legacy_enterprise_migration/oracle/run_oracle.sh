#!/usr/bin/env bash
# Golden-output oracle for POSTTRAN (CBTRN02C).
# Usage: [SCENARIO=<name>] [DALYTRAN_SRC=<file>] oracle/run_oracle.sh
#   default scenario "posttran" runs CardDemo's own sample transactions; any other scenario runs DALYTRAN_SRC
#   (350-byte fixed records, line breaks tolerated) through the same COBOL and stores it in golden/<scenario>/.
#   STATE_DIR=<dir>   start from custom initial files (acctdata.txt cardxref.txt tcatbal.txt discgrp.txt ...) instead of
#                     CardDemo's samples, so interest/posting edge cases can be built from exact balances and rates.
#   STAGES="posttran intcalc"   which programs to run, in order, on the same data (default: both for the sample
#                     scenario, posttran only otherwise). intcalc output goes to golden/<scenario>/intcalc/.
#   INT_DATE=2022-07-01   PARM date for INTCALC (becomes the interest-transaction id prefix).
# Reloads CardDemo sample data from scratch, runs the real COBOL program under GnuCOBOL,
# and snapshots everything it produces into oracle/golden/posttran/.
# The COBOL run mutates its own data, so a fresh reload before EVERY run is mandatory.
#
# Env: BASE  working dir holding bin/ data/ out/ (default ~/carddemo-env-local; /opt/carddemo-env on the VM)
#      SRC   CardDemo checkout's app/ dir (default $BASE/carddemo/app)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ENVDIR="$HERE/../gcp-legacy-env"
export BASE="${BASE:-$HOME/carddemo-env-local}"
export SRC="${SRC:-$BASE/carddemo/app}"
D="$BASE/data"; B="$BASE/bin"; OUT="$BASE/out"; SCENARIO="${SCENARIO:-posttran}"; G="$HERE/golden/$SCENARIO"
mkdir -p "$OUT" "$G" "$BASE/stubs"

[ -d "$SRC" ] || { echo "CardDemo source not found at $SRC (git clone aws-samples/aws-mainframe-modernization-carddemo)"; exit 1; }
[ -x "$B/CBTRN02C" ] || { cp -R "$ENVDIR/stubs/." "$BASE/stubs/"; bash "$ENVDIR/build.sh" >/dev/null; }

# macOS GnuCOBOL looks for .dylib; the env scripts emit .so (harmless on Linux)
if [ "$(uname)" = "Darwin" ]; then for f in "$B"/*.so; do ln -sf "$f" "${f%.so}.dylib"; done; fi

# dump helpers (full raw records of the final account / category-balance state)
for p in DUMPACCT DUMPTCAT; do
  [ -x "$B/$p" ] || cobc -x -fsign=EBCDIC "$HERE/stubs/$p.cbl" -o "$B/$p"
done

EFFECTIVE="$SRC"
if [ -n "${STATE_DIR:-}" ]; then                       # overlay: CardDemo ASCII dir with our files swapped in
  EFFECTIVE="$BASE/overlay"; rm -rf "$EFFECTIVE"; mkdir -p "$EFFECTIVE/data"
  cp -R "$SRC/data/ASCII" "$EFFECTIVE/data/ASCII"; cp "$STATE_DIR"/*.txt "$EFFECTIVE/data/ASCII/"
fi
SRC="$EFFECTIVE" bash "$ENVDIR/load-data.sh" >/dev/null 2>&1           # fresh data every run
if [ -n "${DALYTRAN_SRC:-}" ]; then tr -d '\r\n' < "$DALYTRAN_SRC" > "$D/DALYTRAN.ps"; fi   # custom daily transactions
export COB_LIBRARY_PATH="$B"
export DD_DALYTRAN="$D/DALYTRAN.ps" DD_TRANFILE="$D/TRANSACT.vsam" DD_XREFFILE="$D/CARDXREF.vsam"
export DD_ACCTFILE="$D/ACCTDATA.vsam" DD_TCATBALF="$D/TCATBALF.vsam" DD_DALYREJS="$OUT/DALYREJS.ps"

set +e; "$B/CBTRN02C" > "$G/stdout.txt" 2>&1; RC=$?; set -e
echo "$RC" > "$G/rc.txt"
cp "$OUT/DALYREJS.ps" "$G/DALYREJS.ps"
DD_FLATOUT="$G/TRANSACT.flat" "$B/TRANFLAT"            # posted transactions, 350-byte records
DD_FLATOUT="$G/ACCTDATA.flat" "$B/DUMPACCT"            # final accounts, 300-byte records
DD_FLATOUT="$G/TCATBALF.flat" "$B/DUMPTCAT"            # final category balances, 50-byte records
cp "$D/DALYTRAN.ps" "$G/DALYTRAN.input"                # the exact input, for the Java side
mkdir -p "$G/input"                                    # initial state the COBOL loaded (CR stripped), so the
for f in acctdata cardxref tcatbal discgrp; do tr -d '\r' < "$EFFECTIVE/data/ASCII/$f.txt" > "$G/input/$f.txt"; done  # Java side runs standalone

if [ "$SCENARIO" = "posttran" ]; then DEFAULT_STAGES="posttran intcalc"; else DEFAULT_STAGES="posttran"; fi
case " ${STAGES:-$DEFAULT_STAGES} " in *" intcalc "*)
  GI="$G/intcalc"; mkdir -p "$GI"; INT_DATE="${INT_DATE:-2022-07-01}"
  export DD_DISCGRP="$D/DISCGRP.vsam" DD_CARDXREF="$D/CARDXREF.vsam" DD_TRANSACT="$OUT/SYSTRAN.ps"; rm -f "$OUT/SYSTRAN.ps"
  set +e; "$B/RUNCBACT04C" "$INT_DATE" > "$GI/stdout.txt" 2>&1; IRC=$?; set -e
  echo "$IRC" > "$GI/rc.txt"; echo "$INT_DATE" > "$GI/date.txt"
  cp "$OUT/SYSTRAN.ps" "$GI/SYSTRAN.ps" 2>/dev/null || : > "$GI/SYSTRAN.ps"
  DD_FLATOUT="$GI/ACCTDATA.flat" "$B/DUMPACCT"; DD_FLATOUT="$GI/TCATBALF.flat" "$B/DUMPTCAT"
  echo "INTCALC rc=$IRC  ($(( $(wc -c < "$GI/SYSTRAN.ps") / 350 )) interest transactions)";;
esac
echo "POSTTRAN rc=$RC  ($(grep -h 'PROCESSED\|REJECTED' "$G/stdout.txt" | tr -s ' ' | tr '\n' ' '))"
( cd "$G" && wc -c DALYREJS.ps TRANSACT.flat ACCTDATA.flat TCATBALF.flat )
