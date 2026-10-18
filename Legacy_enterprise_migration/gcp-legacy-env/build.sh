#!/usr/bin/env bash
# Compile CardDemo batch programs + stubs with GnuCOBOL.
set -uo pipefail
BASE="${BASE:-/opt/carddemo-env}"
SRC="${SRC:-$BASE/carddemo/app}"
BIN="$BASE/bin"; mkdir -p "$BIN"
FLAGS="-fsign=EBCDIC -I $SRC/cpy"   # data files use EBCDIC-style signed overpunch ({ A-I } J-R)

# IBM Language Environment abend routine used by the batch programs
cobc -m $FLAGS "$BASE/stubs/CEE3ABD.cbl" -o "$BIN/CEE3ABD.so" || exit 1

ok=(); fail=()
for p in CBACT01C CBACT02C CBACT03C CBCUS01C CBTRN01C CBTRN02C CBTRN03C COBSWAIT; do
  f=$(ls "$SRC"/cbl/$p.[cC][bB][lL] 2>/dev/null | head -1)
  [ -n "$f" ] || { fail+=("$p(missing)"); continue; }
  if cobc -x $FLAGS "$f" -o "$BIN/$p" 2> "$BIN/$p.err"; then ok+=("$p"); else fail+=("$p"); fi
done
# CBACT04C takes a JCL PARM, so build it as a module plus a launcher
f=$(ls "$SRC"/cbl/CBACT04C.[cC][bB][lL] | head -1)
if cobc -m $FLAGS "$f" -o "$BIN/CBACT04C.so" 2> "$BIN/CBACT04C.err" &&    cobc -x $FLAGS "$BASE/stubs/RUNCBACT04C.cbl" -o "$BIN/RUNCBACT04C"; then ok+=("CBACT04C"); else fail+=("CBACT04C"); fi
# helper programs: readers for the indexed files and the TRANREPT flat-file step
for p in ACCTDUMP TCATDUMP TRANFLAT; do
  cobc -x $FLAGS "$BASE/stubs/$p.cbl" -o "$BIN/$p" 2> "$BIN/$p.err" || echo "helper $p failed (see $BIN/$p.err)"
done
# callable utility module
cobc -m $FLAGS "$SRC/cbl/CSUTLDTC.cbl" -o "$BIN/CSUTLDTC.so" 2>/dev/null || true

echo "BUILT:  ${ok[*]:-none}"
echo "FAILED: ${fail[*]:-none}   (errors in $BIN/<prog>.err)"
