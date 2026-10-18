#!/usr/bin/env bash
# Runs the core nightly flow: POSTTRAN (CBTRN02C) -> INTCALC (CBACT04C) -> transaction report (CBTRN03C).
BASE="${BASE:-/opt/carddemo-env}"; D="$BASE/data"; B="$BASE/bin"; OUT="$BASE/out"; mkdir -p "$OUT"
export COB_LIBRARY_PATH="$B"
# DD-name -> file mappings (GnuCOBOL reads DD_<name>)
export DD_DALYTRAN="$D/DALYTRAN.ps"  DD_TRANFILE="$D/TRANSACT.vsam" DD_XREFFILE="$D/CARDXREF.vsam"
export DD_CARDXREF="$D/CARDXREF.vsam" DD_ACCTFILE="$D/ACCTDATA.vsam" DD_TCATBALF="$D/TCATBALF.vsam"
export DD_DISCGRP="$D/DISCGRP.vsam"  DD_TRANSACT="$OUT/SYSTRAN.ps" DD_DALYREJS="$OUT/DALYREJS.ps"
export DD_TRANTYPE="$D/TRANTYPE.vsam" DD_TRANCATG="$D/TRANCATG.vsam" DD_TRANREPT="$OUT/TRANREPT.txt"
export DD_CUSTFILE="$D/CUSTDATA.vsam" DD_CARDFILE="$D/CARDDATA.vsam"
echo "== POSTTRAN (CBTRN02C)";  "$B/CBTRN02C"; echo "rc=$?"
echo "== INTCALC (CBACT04C)";   "$B/RUNCBACT04C" "$(date +%Y-%m-%d)"; echo "rc=$?"

# TRANREPT.jcl step 1-2: copy the indexed transaction file to a flat file and sort it by card number
echo "== TRANREPT (CBTRN03C)"
DD_FLATOUT="$OUT/TRAN.flat" "$B/TRANFLAT"
python3 -c "
d=open('$OUT/TRAN.flat','rb').read(); r=[d[i:i+350] for i in range(0,len(d),350)]
r.sort(key=lambda x:x[262:278]); open('$OUT/TRAN.sorted','wb').write(b''.join(r))"
printf '%-80s' "${REPORT_RANGE:-2022-01-01 2099-12-31}" > "$OUT/DATEPARM.txt"
DD_TRANFILE="$OUT/TRAN.sorted" DD_DATEPARM="$OUT/DATEPARM.txt" "$B/CBTRN03C" >/dev/null; echo "rc=$?"
echo "Report: fold -w133 $OUT/TRANREPT.txt | less"
echo "Outputs in $OUT"; ls -l "$OUT"
