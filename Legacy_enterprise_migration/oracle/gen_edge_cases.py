#!/usr/bin/env python3
"""Generate a targeted daily-transaction file that exercises every POSTTRAN business rule, including boundaries.

The sample data only ever triggers the "over limit" rejection, so a migrated program can pass it while being wrong.
This builds cases from the REAL initial state (accounts, limits, balances, cards) so boundaries are exact.
It decides inputs only; the expected outputs come from running the real COBOL (oracle/run_oracle.sh).

  oracle/gen_edge_cases.py            -> oracle/scenarios/edge/DALYTRAN.input + cases.json
"""
import json, random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = HERE / "golden/posttran/input"
OUT = HERE / "scenarios/edge"

POS, NEG = "{ABCDEFGHI", "}JKLMNOPQR"

def dec(f, scale=2):
    d = POS.find(f[-1]); neg = False
    if d < 0: d = NEG.find(f[-1]); neg = True
    v = Decimal(int(f[:-1] + str(d))).scaleb(-scale)
    return -v if neg else v

def enc(v, int_digits=9, scale=2):
    n = int(abs(Decimal(v)).scaleb(scale)); s = f"{n:0{int_digits + scale}d}"
    return s[:-1] + (NEG if Decimal(v) < 0 else POS)[int(s[-1])]

def load_state():
    xref = [l.rstrip("\n").ljust(50) for l in (STATE / "cardxref.txt").read_text().splitlines() if l]
    accts = {}
    for l in (STATE / "acctdata.txt").read_text().splitlines():
        l = l.ljust(300)
        accts[l[:11]] = dict(limit=dec(l[24:36]), cc=dec(l[78:90]), cd=dec(l[90:102]), expiry=l[58:68], card=None)
    for x in xref:
        if x[25:36] in accts and accts[x[25:36]]["card"] is None: accts[x[25:36]]["card"] = x[:16]
    return accts

def main():
    A = load_state()
    ids = sorted(a for a in A if A[a]["card"] and A[a]["expiry"] >= "2023-01-01")
    rnd = random.Random(20261017)
    recs = []   # (label, category, record)
    n = 0

    def tx(label, category, acct=None, amt=Decimal("10.00"), card=None, odate="2022-06-10", type_cd="01", cat=1,
           desc="EDGE CASE", merchant="Edge Merchant", city="Testville"):
        nonlocal n
        n += 1
        card = card or A[acct]["card"]
        r = (f"@@{n:014d}"                       # placeholder id, reassigned (shuffled) below
             + type_cd + f"{cat:04d}" + "POS TERM  " + f"{desc:<100.100}" + enc(amt) + f"{n:09d}"
             + f"{merchant:<50.50}" + f"{city:<50.50}" + "12345     " + f"{card:<16.16}"
             + f"{odate} 19:27:53.000000" + " " * 26 + " " * 20)
        assert len(r) == 350, len(r)
        recs.append([label, category, r])

    def day(s, k): return (date.fromisoformat(s) + timedelta(days=k)).isoformat()
    free = iter(ids)
    def acct(): return next(free)

    # --- credit-limit boundary (tempBal = cycCredit - cycDebit + amt; reject only if limit < tempBal)
    a = acct(); s = A[a]; tx("amount makes balance EXACTLY equal the credit limit -> accepted", "limit-boundary", a, s["limit"] - (s["cc"] - s["cd"]))
    a = acct(); s = A[a]; tx("balance one cent OVER the limit -> reject 102", "limit-boundary", a, s["limit"] - (s["cc"] - s["cd"]) + Decimal("0.01"))
    a = acct(); s = A[a]; tx("balance one cent UNDER the limit -> accepted", "limit-boundary", a, s["limit"] - (s["cc"] - s["cd"]) - Decimal("0.01"))
    # --- expiry boundary (reject 103 only if expiry < transaction date)
    a = acct(); tx("transaction dated exactly on expiry date -> accepted", "expiry-boundary", a, Decimal("5.00"), odate=A[a]["expiry"])
    a = acct(); tx("transaction one day after expiry -> reject 103", "expiry-boundary", a, Decimal("5.00"), odate=day(A[a]["expiry"], 1))
    a = acct(); s = A[a]; tx("over limit AND expired -> 103 overwrites 102", "rule-priority", a, s["limit"] + Decimal("1.00"), odate=day(s["expiry"], 30))
    # --- stale-balance sequence: same account, same chunk; later rows must see earlier postings
    a = acct(); s = A[a]; room = s["limit"] - (s["cc"] - s["cd"])
    tx("sequence 1/3: leaves exactly 100.00 of headroom -> accepted", "sequential-state", a, room - Decimal("100.00"))
    tx("sequence 2/3: uses the last 100.00 -> accepted (balance == limit)", "sequential-state", a, Decimal("100.00"))
    tx("sequence 3/3: one cent more -> reject 102 (needs balance from rows 1-2)", "sequential-state", a, Decimal("0.01"))
    # --- unknown cards
    tx("card number not in cross-reference -> reject 100", "unknown-card", card="9999999999999999")
    tx("blank card number -> reject 100", "unknown-card", card=" " * 16)
    c = A[acct()]["card"]; tx("card differing from a real one in last digit -> reject 100", "unknown-card", card=c[:-1] + ("0" if c[-1] != "0" else "1"))
    # --- zero / negative amounts (credit branch is amt >= 0)
    a = acct(); tx("zero amount counts as credit", "sign-handling", a, Decimal("0.00"))
    tx("negative cent (payment)", "sign-handling", a, Decimal("-0.01"))
    tx("large payment", "sign-handling", a, Decimal("-5000.00"))
    tx("purchase after payment", "sign-handling", a, Decimal("120.50"))
    # --- every overpunch final digit, both signs
    a = acct()
    for d in range(10):
        tx(f"overpunch digit +{d}", "overpunch", a, Decimal(f"{d + 1}.0{d}"))
        tx(f"overpunch digit -{d}", "overpunch", a, -Decimal(f"{d + 1}.0{d}"))
    # --- arithmetic overflow of WS-TEMP-BAL (S9(09)V99): legacy truncates high-order digits
    a = acct(); tx("seed credit so next row overflows 9 digits", "overflow", a, Decimal("100.00"))
    tx("999,999,999.99 purchase: temp balance wraps past 9 digits", "overflow", a, Decimal("999999999.99"))
    a = acct(); tx("max negative amount", "overflow", a, Decimal("-999999999.99"))
    tx("max negative amount again", "overflow", a, Decimal("-999999999.99"))
    # --- category balance create / update (new keys, existing keys, varied type & category codes)
    a = acct()
    for i, (t, c) in enumerate([("01", 9), ("05", 7), ("01", 9), ("07", 1), ("05", 7), ("02", 9999)]):
        tx(f"category ({t},{c}) {'create' if (t, c) not in [x for x in []] else ''}", "category-balance", a, Decimal("7.77") * (i + 1), type_cd=t, cat=c)
    # --- byte transparency (non-ASCII / punctuation / full-length text)
    a = acct()
    tx("latin-1 and punctuation in free text", "text-fidelity", a, Decimal("42.00"), desc="Café & Crème <50%> 'quoted' #1", merchant="Müller & Söhne GmbH", city="Zürich")
    tx("fields filled to full width", "text-fidelity", a, Decimal("1.00"), desc="D" * 100, merchant="M" * 50, city="C" * 50)
    # --- realistic mixed traffic on remaining accounts (seeded, reproducible)
    for a in free:
        s = A[a]
        for _ in range(rnd.choice([1, 2, 3])):
            kind = rnd.choice(["purchase"] * 5 + ["payment", "huge", "stale"])
            amt = {"purchase": Decimal(rnd.randint(100, 40000)) / 100, "payment": -Decimal(rnd.randint(100, 90000)) / 100,
                   "huge": s["limit"] * Decimal(rnd.choice([1, 2, 10])), "stale": Decimal(rnd.randint(1, 99)) / 100}[kind]
            tx(f"mixed traffic: {kind}", "mixed-traffic", a, amt, type_cd=rnd.choice(["01", "02", "03"]), cat=rnd.choice([1, 2, 3, 4]),
               odate=rnd.choice(["2022-03-01", "2022-06-10", "2022-12-31", "2023-02-01"]))

    # file order stays as built (sequence rows must stay adjacent); IDs are shuffled so key order != arrival order
    id_pool = [f"9{i:015d}" for i in rnd.sample(range(1, 10_000), len(recs))]
    cases, out = {}, []
    for (label, cat, r), tid in zip(recs, id_pool):
        out.append(tid + r[16:]); cases[tid] = {"label": label, "category": cat}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "DALYTRAN.input").write_bytes("".join(out).encode("latin-1"))
    (OUT / "cases.json").write_text(json.dumps(cases, indent=1, ensure_ascii=False))
    cats = {}
    for c in cases.values(): cats[c["category"]] = cats.get(c["category"], 0) + 1
    print(f"{len(out)} transactions -> {OUT}/DALYTRAN.input"); print(cats)

if __name__ == "__main__":
    main()
