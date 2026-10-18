#!/usr/bin/env python3
"""Differential verifier: compare a migrated batch program run against the COBOL golden output.

Compares fixed-width record files field by field, masks fields that are legitimately non-deterministic
(the processed-timestamp), and emits a machine-readable report (JSON) plus a human summary.
Exit code 0 = every artifact identical, 1 = mismatches found. No LLM involved: ground truth is the real COBOL run.

  verify.py [--program posttran|intcalc] --golden oracle/golden/posttran[/intcalc] --candidate <java output dir> [--json report.json]
"""
import argparse, json, sys
from pathlib import Path

# (name, offset, length). Layouts from the CardDemo copybooks.
TRAN = [("TRAN-ID",0,16),("TRAN-TYPE-CD",16,2),("TRAN-CAT-CD",18,4),("TRAN-SOURCE",22,10),("TRAN-DESC",32,100),
        ("TRAN-AMT",132,11),("TRAN-MERCHANT-ID",143,9),("TRAN-MERCHANT-NAME",152,50),("TRAN-MERCHANT-CITY",202,50),
        ("TRAN-MERCHANT-ZIP",252,10),("TRAN-CARD-NUM",262,16),("TRAN-ORIG-TS",278,26),("TRAN-PROC-TS",304,26),
        ("FILLER",330,20)]
ACCT = [("ACCT-ID",0,11),("ACCT-ACTIVE-STATUS",11,1),("ACCT-CURR-BAL",12,12),("ACCT-CREDIT-LIMIT",24,12),
        ("ACCT-CASH-CREDIT-LIMIT",36,12),("ACCT-OPEN-DATE",48,10),("ACCT-EXPIRAION-DATE",58,10),
        ("ACCT-REISSUE-DATE",68,10),("ACCT-CURR-CYC-CREDIT",78,12),("ACCT-CURR-CYC-DEBIT",90,12),
        ("ACCT-ADDR-ZIP",102,10),("ACCT-GROUP-ID",112,10),("FILLER",122,178)]
TCAT = [("TRANCAT-ACCT-ID",0,11),("TRANCAT-TYPE-CD",11,2),("TRANCAT-CD",13,4),("TRAN-CAT-BAL",17,11),("FILLER",28,22)]
REJ  = [("REJECT-TRAN-DATA",0,350),("VALIDATION-FAIL-REASON",350,4),("VALIDATION-FAIL-REASON-DESC",354,76)]

# program -> artifact file -> (record length, layout, key (name, offset, length), masked field names).
# Records are aligned BY KEY, so one missing/extra record does not make every later record look wrong.
# Masked = fields that legitimately come from the system clock.
PROGRAMS = {
    "posttran": {                                   # CBTRN02C
        "TRANSACT.flat": (350, TRAN, ("TRAN-ID", 0, 16), {"TRAN-PROC-TS"}),
        "DALYREJS.ps":   (430, REJ,  ("TRAN-ID", 0, 16), set()),
        "ACCTDATA.flat": (300, ACCT, ("ACCT-ID", 0, 11), set()),
        "TCATBALF.flat": (50,  TCAT, ("TRANCAT-KEY", 0, 17), set()),
    },
    "intcalc": {                                    # CBACT04C
        "SYSTRAN.ps":    (350, TRAN, ("TRAN-ID", 0, 16), {"TRAN-ORIG-TS", "TRAN-PROC-TS"}),
        "ACCTDATA.flat": (300, ACCT, ("ACCT-ID", 0, 11), set()),
    },
}
ARTIFACTS = PROGRAMS["posttran"]

def split(data, rl):
    return [data[i:i+rl] for i in range(0, len(data), rl)]

def field(rec, f):
    return rec[f[1]:f[1]+f[2]].decode("latin-1")

def keyed(records, key):
    """[(key text, nth occurrence, record)] so even duplicate keys align deterministically."""
    seen, out = {}, []
    for r in records:
        k = r[key[1]:key[1] + key[2]].decode("latin-1"); n = seen.get(k, 0); seen[k] = n + 1
        out.append(((k, n), r))
    return out

def compare(name, gold_p, cand_p, max_listed=20):
    rl, layout, key, masked = ARTIFACTS[name]
    if not cand_p.exists():
        return {"artifact": name, "status": "MISSING", "golden_records": None, "matched": 0, "mismatches": [], "mismatch_count": 0}
    G, C = keyed(split(gold_p.read_bytes(), rl), key), keyed(split(cand_p.read_bytes(), rl), key)
    cmap = dict(C)
    mism, matched = [], 0
    for kk, g in G:
        c = cmap.get(kk)
        if c is None:
            mism.append({"key": kk[0], "problem": "missing from candidate (COBOL produced it)"}); continue
        diffs = [{"field": f[0], "expected": field(g, f), "actual": field(c, f)}
                 for f in layout if f[0] not in masked and field(g, f) != field(c, f)]
        if diffs: mism.append({"key": kk[0], "diffs": diffs})
        else: matched += 1
    gkeys = {kk for kk, _ in G}
    for kk, _ in C:
        if kk not in gkeys: mism.append({"key": kk[0], "problem": "extra in candidate (COBOL did not produce it)"})
    common_g = [kk for kk, _ in G if kk in cmap]; common_c = [kk for kk, _ in C if kk in gkeys]
    order_ok = common_g == common_c
    problems = sum(1 for m in mism if "problem" in m)
    return {"artifact": name, "status": "IDENTICAL" if not mism and order_ok else "MISMATCH",
            "golden_records": len(G), "candidate_records": len(C), "matched": matched,
            "missing": sum(1 for m in mism if "missing" in m.get("problem", "")),
            "extra": sum(1 for m in mism if "extra" in m.get("problem", "")),
            "different": len(mism) - problems, "order_matches": order_ok,
            "masked_fields": sorted(masked), "mismatches": mism[:max_listed], "mismatch_count": len(mism)}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", required=True); ap.add_argument("--candidate", required=True)
    ap.add_argument("--json"); ap.add_argument("--program", default="posttran", choices=PROGRAMS); a = ap.parse_args()
    global ARTIFACTS; ARTIFACTS = PROGRAMS[a.program]
    G, C = Path(a.golden), Path(a.candidate)
    results = [compare(n, G/n, C/n) for n in ARTIFACTS]
    rc_ok = (G/"rc.txt").read_text().strip() == (C/"rc.txt").read_text().strip() if (C/"rc.txt").exists() else False
    def counts(p): return [l for l in p.read_text().splitlines() if "PROCESSED" in l or "REJECTED" in l] if p.exists() else []
    counts_ok = counts(G/"stdout.txt") == counts(C/"stdout.txt")     # intcalc has no counters: both lists are empty
    total = sum(r["golden_records"] or 0 for r in results); good = sum(r["matched"] for r in results)
    report = {"return_code_matches": rc_ok, "counters_match": counts_ok, "records_total": total, "records_matched": good,
              "record_match_rate": round(good/total, 4) if total else 0, "artifacts": results,
              "verdict": "PASS" if rc_ok and counts_ok and all(r["status"] == "IDENTICAL" for r in results) else "FAIL"}
    if a.json: Path(a.json).write_text(json.dumps(report, indent=2))
    print(f"{'artifact':<16}{'status':<11}{'matched':>14}")
    for r in results:
        print(f"{r['artifact']:<16}{r['status']:<11}{r['matched']:>7}/{r['golden_records'] or 0:<6}")
        if r["status"] == "MISMATCH":
            print(f"    differing {r['different']}  missing {r['missing']}  extra {r['extra']}  order {'same' if r['order_matches'] else 'DIFFERENT'}")
        for m in r["mismatches"][:3]:
            for d in m.get("diffs", [{"field": m.get("problem")}])[:3]:
                print(f"    key {m['key']} {d['field']}: expected {d.get('expected')!r} got {d.get('actual')!r}")
    print(f"return code {'OK' if rc_ok else 'DIFFERS'} | counters {'OK' if counts_ok else 'DIFFER'} | "
          f"records {good}/{total} ({report['record_match_rate']:.2%}) | VERDICT: {report['verdict']}")
    sys.exit(0 if report["verdict"] == "PASS" else 1)

if __name__ == "__main__":
    main()
