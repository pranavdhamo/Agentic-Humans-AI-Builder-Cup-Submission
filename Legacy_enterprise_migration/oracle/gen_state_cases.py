#!/usr/bin/env python3
"""Scenario for COBOL's hidden working-storage state when creating category-balance records (CBTRN02C, 2700-A).

A newly created TRAN-CAT-BAL record does NOT get a fresh FILLER: INITIALIZE skips FILLER, so it keeps whatever the last
SUCCESSFULLY READ category record left in the buffer (spaces if nothing was read yet). In the sample data every existing
record has an all-zero filler, so a translation that simply writes zeros passes every other scenario. Here each existing
record gets a distinctive filler, and creates are placed before any read, after reads, and after a rejected transaction.

  oracle/gen_state_cases.py  -> oracle/scenarios/hidden-state/{state/tcatbal.txt, DALYTRAN.input, cases.json}
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SAMPLE = HERE / "golden/posttran/input"
OUT = HERE / "scenarios/hidden-state"
POS = "{ABCDEFGHI"

def enc(cents, int_digits=9):
    s = f"{cents:0{int_digits + 2}d}"
    return s[:-1] + POS[int(s[-1])]

def main():
    xref = {l[25:36]: l[:16] for l in (SAMPLE / "cardxref.txt").read_text().splitlines() if l}
    tcat = [l.ljust(50) for l in (SAMPLE / "tcatbal.txt").read_text().splitlines() if l]
    # distinctive filler per existing record: F01..., so inherited filler is traceable to the record that was read
    marked = [l[:28] + f"F{int(l[:11]):02d}".ljust(22, chr(ord('a') + int(l[:11]) % 20)) for l in tcat]
    (OUT / "state").mkdir(parents=True, exist_ok=True)
    (OUT / "state/tcatbal.txt").write_text("\n".join(marked) + "\n")

    n, recs, cases = 0, [], {}
    def tx(acct, type_cd, cat, cents, label, card=None):
        nonlocal n
        n += 1; tid = f"{8000000000000000 + n:016d}"
        r = (tid + type_cd + f"{cat:04d}" + "POS TERM  " + f"{'HIDDEN STATE CASE':<100}" + enc(cents) + f"{n:09d}"
             + f"{'State Merchant':<50}" + f"{'Statetown':<50}" + "12345     " + (card or xref[acct]) + "2022-06-10 19:27:53.000000" + " " * 26 + " " * 20)
        assert len(r) == 350; recs.append(r); cases[tid] = label
    a1, a2, a3 = "00000000001", "00000000002", "00000000003"
    tx(a1, "01", 7, 1000, "CREATE before any category record was read -> filler is the initial spaces")
    tx(a1, "01", 1, 500, "update existing record: buffer now holds this record's filler (F01...)")
    tx(a1, "01", 8, 1000, "CREATE after a read -> inherits the filler of the last record read (F01...)")
    tx(a2, "01", 1, 500, "update existing record of another account (F02...)")
    tx(a2, "01", 9, 1000, "CREATE -> inherits F02...")
    tx(None, "01", 1, 100, "rejected (unknown card): must not touch the category buffer", card="9999999999999999")
    tx(a3, "01", 10, 1000, "CREATE after a rejected transaction -> still inherits F02...")
    tx(a3, "01", 1, 500, "update existing record (F03...)")
    tx(a3, "01", 1, 250, "update the same record again")
    tx(a3, "02", 1, 1000, "CREATE -> inherits F03...")
    (OUT / "DALYTRAN.input").write_bytes("".join(recs).encode("latin-1"))
    (OUT / "cases.json").write_text(json.dumps(cases, indent=1))
    print(f"hidden-state: {len(recs)} transactions, {len(marked)} category records with distinctive filler")

if __name__ == "__main__":
    main()
