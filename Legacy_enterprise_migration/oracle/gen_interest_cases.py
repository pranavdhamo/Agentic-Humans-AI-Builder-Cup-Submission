#!/usr/bin/env python3
"""Generate initial-state scenarios that exercise every rule of the monthly-interest program (CBACT04C).

The sample data never triggers truncation corner cases, negative balances, zero rates, overflow, rate-group
fallback, or the abend paths. Each scenario is a custom initial state (accounts, card xref, category balances,
disclosure-group rates); the expected outputs come from running the REAL COBOL on it (oracle/run_oracle.sh).

  oracle/gen_interest_cases.py   -> oracle/scenarios/<name>/{state/*.txt, DALYTRAN.input, cases.json}
Scenarios: interest-edge (no abend), interest-abend-account, interest-abend-xref, interest-abend-rate.
"""
import json, random
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
SAMPLE = HERE / "golden/posttran/input"
POS, NEG = "{ABCDEFGHI", "}JKLMNOPQR"

def enc(v, int_digits, scale=2):
    v = Decimal(v); n = int(abs(v).scaleb(scale)); s = f"{n:0{int_digits + scale}d}"
    return s[:-1] + (NEG if v < 0 else POS)[int(s[-1])]

def default_rows():
    rows = []
    for l in (SAMPLE / "discgrp.txt").read_text().splitlines():
        if l.startswith("DEFAULT"): rows.append((l[10:12], l[12:16]))
    return rows                                   # (type, category) pairs that have a DEFAULT rate row

def build(name, inject=None):
    rnd = random.Random(20261017)
    D = default_rows(); assert len(D) >= 8
    cats = [D[0], D[1], D[2], D[3], D[4]]      # D[4] has a ZERO default rate
    sample_acct = (SAMPLE / "acctdata.txt").read_text().splitlines()[0].ljust(300)
    cases, accts, tcat = {}, [], []             # accts: dict, tcat: (acct, type, cat, bal)

    def acct(label, group="          ", cur="1000.00", limit="5000.00", cc="0.00", cd="0.00"):
        n = len(accts) + 1; aid = f"{10000000000 + n * 7:011d}"
        accts.append(dict(id=aid, group=group, cur=cur, limit=limit, cc=cc, cd=cd, card=f"4{rnd.randrange(10**15):015d}"))
        cases[aid] = label; return aid
    def cat(aid, i, bal): tcat.append((aid, *cats[i % len(cats)], bal))

    a = acct("truncation: per-category truncation, awkward balances (blank group -> DEFAULT rates)")
    for i, b in enumerate(["100.01", "333.33", "0.01", "999999.99"]): cat(a, i, b)
    a = acct("rounding vs truncation: 300.00 and 700.00 at 2.50%% give x.625 and x.4583 (HALF_UP would differ)".replace("%%", "%"))
    for i, b in enumerate(["300.00", "700.00"]): cat(a, i + 1, b)
    a = acct("category whose DEFAULT rate is zero -> no transaction")
    cat(a, 4, "5000.00")
    a = acct("negative balances: negative interest truncates toward zero; -0.01 gives zero", cur="-250.00")
    for i, b in enumerate(["-100.01", "-0.01", "-12345.67"]): cat(a, i, b)
    a = acct("zero balances: zero-amount interest transactions are still written")
    for i, b in enumerate(["0.00", "0.00"]): cat(a, i, b)
    a = acct("ZEROGRP: zero rates -> no transactions, yet cycle credit/debit still reset", group="ZEROGRP   ", cc="800.00", cd="300.00")
    for i, b in enumerate(["500.00", "20.00"]): cat(a, i, b)
    a = acct("HIGHRATE: monthly interest overflows 9 digits", group="HIGHRATE  ", cur="10.00")
    cat(a, 0, "999999999.99")
    a = acct("HIGHRATE: running total overflows 9 digits across categories", group="HIGHRATE  ", cur="5.00")
    for i in range(3): cat(a, i, "48000480.00")
    a = acct("NEGRATE: negative annual rate -> negative interest", group="NEGRATE   ", cur="777.77")
    for i, b in enumerate(["1000.00", "55.55"]): cat(a, i, b)
    a = acct("PARTIAL: one category uses the group rate, the others fall back to DEFAULT", group="PARTIAL   ")
    for i, b in enumerate(["1000.00", "1000.00", "1000.00"]): cat(a, i, b)
    a = acct("current balance near the 10-digit limit: adding interest overflows ACCT-CURR-BAL", cur="9999999999.99", cc="1.00", cd="2.00")
    cat(a, 0, "100000.00")
    a = acct("non-zero cycle credit/debit are reset; balance gets the sum of interest", cur="-42.42", cc="1234.56", cd="999.99")
    for i, b in enumerate(["250.25", "250.25"]): cat(a, i, b)
    for k in range(8):                           # volume of mixed, seeded accounts
        a = acct(f"mixed account {k}", cur=f"{rnd.randint(-5000, 90000) / 100:.2f}")
        for i in range(rnd.choice([1, 2, 3, 4])): cat(a, i, f"{rnd.randint(-100000, 9000000) / 100:.2f}")
    a = acct("LAST account in the file: interest transactions written but balance never updated (legacy bug)")
    for i, b in enumerate(["1500.00", "2500.00"]): cat(a, i, b)

    xref = {x["id"]: x["card"] for x in accts}
    if inject == "account":                      # category balances for an account that is not in the account file
        ghost = "99999999999"; tcat.append((ghost, *cats[0], "100.00")); xref[ghost] = "4999999999999999"; cases[ghost] = "ABEND: account missing"
    if inject == "xref":
        victim = accts[len(accts) // 2]["id"]; del xref[victim]; cases[victim] += "  [ABEND: no card cross-reference]"
    if inject == "rate":
        tcat.append((accts[len(accts) // 2]["id"], "07", "9999", "10.00")); cases[accts[len(accts) // 2]["id"]] += "  [ABEND: no DEFAULT rate row]"

    tcat.sort(key=lambda t: (t[0], t[1], t[2]))
    out = HERE / "scenarios" / name; (out / "state").mkdir(parents=True, exist_ok=True)
    def acct_line(x):
        r = list(sample_acct)
        def put(i, j, s): r[i:j] = list(s.ljust(j - i)[:j - i])
        put(0, 11, x["id"]); put(11, 12, "Y"); put(12, 24, enc(x["cur"], 10)); put(24, 36, enc(x["limit"], 10)); put(36, 48, enc("1000.00", 10))
        put(48, 58, "2015-01-01"); put(58, 68, "2030-12-31"); put(68, 78, "2030-12-31"); put(78, 90, enc(x["cc"], 10)); put(90, 102, enc(x["cd"], 10))
        put(102, 112, "ZIP0000000"); put(112, 122, x["group"]); put(122, 300, " " * 178)
        return "".join(r)
    (out / "state/acctdata.txt").write_text("\n".join(acct_line(x) for x in accts if not (inject == "account" and False)) + "\n")
    (out / "state/cardxref.txt").write_text("\n".join(f"{c}{'0' * 9}{aid}{' ' * 14}" for aid, c in xref.items()) + "\n")
    (out / "state/tcatbal.txt").write_text("\n".join(f"{a}{t}{c}{enc(b, 9)}{'0' * 22}" for a, t, c, b in tcat) + "\n")
    base = (SAMPLE / "discgrp.txt").read_text().rstrip("\n").splitlines()
    extra = []
    for t, c in D: extra.append(f"ZEROGRP   {t}{c}{enc('0', 4)}{'0' * 28}")
    for t, c in D: extra.append(f"HIGHRATE  {t}{c}{enc('9999.99', 4)}{'0' * 28}")
    for t, c in D: extra.append(f"NEGRATE   {t}{c}{enc('-5.00', 4)}{'0' * 28}")
    extra.append(f"PARTIAL   {D[0][0]}{D[0][1]}{enc('31.41', 4)}{'0' * 28}")
    (out / "state/discgrp.txt").write_text("\n".join(base + extra) + "\n")
    (out / "DALYTRAN.input").write_bytes(b"")     # POSTTRAN stage runs on an empty file; INTCALC then sees exactly this state
    (out / "cases.json").write_text(json.dumps(cases, indent=1))
    print(f"{name}: {len(accts)} accounts, {len(tcat)} category balances")

if __name__ == "__main__":
    build("interest-edge")
    build("interest-abend-account", "account")
    build("interest-abend-xref", "xref")
    build("interest-abend-rate", "rate")
