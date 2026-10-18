#!/usr/bin/env python3
"""Prove the verifier can fail: inject plausible translation mistakes into the Java port, rebuild, run, verify.

A mutant is KILLED if at least one scenario of its program no longer matches the COBOL golden output.
A mutant that SURVIVES means no scenario exercises that rule: a test-coverage gap to close.

  mutation_check.py [--only substring]
"""
import argparse, os, subprocess, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scenarios import ROOT, scenarios
from check_all import run_scenario, java_env

PRJ = ROOT / "migrated/carddemo-batch"
SRC = PRJ / "src/main/java/com/agentichumans/carddemo"
JAR = PRJ / "target/carddemo-batch-0.1.0.jar"
ENV = java_env()

PT, IC = "posttran", "intcalc"
EXPIRY = "if (acct.expiryDate().compareTo(tran.origDate()) < 0) {"

# (program, description, file under src/, original text, mutated text)
MUTANTS = [
    # ---- POSTTRAN (CBTRN02C)
    (PT, "negative overpunch decoded as positive", "cobol/CobolNumeric.java", "return negative ? v.negate() : v;", "return v;"),
    (PT, "no high-order truncation on overflow", "cobol/CobolNumeric.java", "BigInteger kept = unscaled.abs().mod(mod);", "BigInteger kept = unscaled.abs();"),
    (PT, "expiry compared with <= (date boundary)", "posttran/PostTranProcessor.java", EXPIRY, EXPIRY.replace("< 0", "<= 0")),
    (PT, "card lookup tolerates last-digit typo", "posttran/PostTranProcessor.java", "Xref xref = ledger.xref.get(tran.cardNum());",
     "Xref xref = ledger.xref.values().stream().filter(x -> x.raw().startsWith(tran.cardNum().substring(0, 15))).findFirst().orElse(null);"),
    (PT, "new category record not created", "posttran/Ledger.java", "tcat.put(key, new TranCatBal(tcatWs.raw()));", "if (!create) tcat.put(key, new TranCatBal(tcatWs.raw()));"),
    (PT, "over-limit uses <= (boundary)", "posttran/PostTranProcessor.java", "creditLimit().compareTo(tempBal) < 0", "creditLimit().compareTo(tempBal) <= 0"),
    (PT, "expiry check does not overwrite 102", "posttran/PostTranProcessor.java", EXPIRY, EXPIRY.replace("if (", "if (reason == 0 && ")),
    (PT, "expiry check dropped", "posttran/PostTranProcessor.java", EXPIRY, "if (false) {"),
    (PT, "debit/credit branch swapped", "posttran/Ledger.java", "if (amt.signum() >= 0) acct.cycCredit", "if (amt.signum() < 0) acct.cycCredit"),
    (PT, "FILLER ignores carried-over COBOL state", "posttran/Ledger.java", "tcatWs.setKey(key);",
     "tcatWs = new TranCatBal(\"0\".repeat(11)+\"  \"+\"0000\"+\"0\".repeat(11)+\" \".repeat(22)); tcatWs.setKey(key);"),
    (PT, "FILLER hard-coded to zeros (right on sample data, wrong in general)", "posttran/Ledger.java", "tcatWs.setKey(key);",
     "tcatWs = new TranCatBal(\"0\".repeat(11)+\"  \"+\"0000\"+\"0\".repeat(11)+\"0\".repeat(22)); tcatWs.setKey(key);"),
    (PT, "TEMP-BAL not truncated to 9 digits", "posttran/PostTranProcessor.java",
     "CobolNumeric.fit(\n                        acct.cycCredit().subtract(acct.cycDebit()).add(tran.amt()), 9, 2)",
     "acct.cycCredit().subtract(acct.cycDebit()).add(tran.amt())"),
    (PT, "account update skipped", "posttran/PostTranProcessor.java", "        ledger.updateAccount(acct, tran.amt());", "        /* skipped */"),
    (PT, "invalid-card reject code 101 instead of 100", "posttran/PostTranProcessor.java", "reason = 100;", "reason = 101;"),
    # ---- INTCALC (CBACT04C)
    (IC, "interest rounds HALF_UP instead of truncating", "intcalc/InterestProcessor.java", "divide(BigDecimal.valueOf(1200), 2, RoundingMode.DOWN)", "divide(BigDecimal.valueOf(1200), 2, RoundingMode.HALF_UP)"),
    (IC, "last account settled (legacy bug 'fixed')", "intcalc/InterestProcessor.java", "if (fixLastAccount && !firstTime && state.abend == null) updateAccount();", "if (!firstTime && state.abend == null) updateAccount();"),
    (IC, "cycle credit not reset", "intcalc/InterestProcessor.java", "        a.cycCredit(BigDecimal.ZERO);\n", ""),
    (IC, "cycle debit not reset", "intcalc/InterestProcessor.java", "        a.cycDebit(BigDecimal.ZERO);\n", ""),
    (IC, "account untouched when interest total is zero", "intcalc/InterestProcessor.java", "        Account a = ledger.accountWs;\n", "        if (totalInt.signum() == 0) return;\n        Account a = ledger.accountWs;\n"),
    (IC, "group-specific rate rows ignored (always DEFAULT)", "intcalc/InterestProcessor.java", "ledger.discGroups.get(groupId + typeCd + catCd);", "null;"),
    (IC, "zero-rate categories still write a transaction", "intcalc/InterestProcessor.java", "if (rate.signum() == 0) return null;", ""),
    # Not listed: "monthly interest not truncated to 9 digits" is an EQUIVALENT mutant. encodeSigned() and the running
    # total both truncate the same way later, so no output can differ and no test could ever kill it.
    (IC, "running total not truncated to 9 digits", "intcalc/InterestProcessor.java", "totalInt = CobolNumeric.fit(totalInt.add(monthly), 9, 2);", "totalInt = totalInt.add(monthly);"),
    (IC, "interest category code wrong (0004 not 0005)", "intcalc/InterestProcessor.java", '"01" + "0005"', '"01" + "0004"'),
    (IC, "missing account skipped instead of abend", "intcalc/InterestProcessor.java", 'if (acct == null) return abend("ACCOUNT NOT FOUND: " + acctId);', "if (acct == null) return null;"),
    (IC, "missing xref skipped instead of abend", "intcalc/InterestProcessor.java", 'if (xref == null) return abend("ACCOUNT NOT FOUND IN XREF: " + acctId);', "if (xref == null) return null;"),
    (IC, "missing DEFAULT rate treated as zero instead of abend", "intcalc/InterestProcessor.java", 'if (d == null) { abend("ERROR READING DEFAULT DISCLOSURE GROUP: " + typeCd + catCd); return false; }', "if (d == null) return false;"),
    (IC, "transaction id suffix starts at 0", "intcalc/InterestProcessor.java", "tranIdSuffix = (tranIdSuffix + 1) % 1_000_000;", "tranIdSuffix = tranIdSuffix % 1_000_000;"),
]


def build():
    return subprocess.run(["mvn", "-q", "-DskipTests", "package"], cwd=PRJ, env=ENV, capture_output=True, text=True).returncode == 0


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--only", default="")
    a = ap.parse_args()
    all_sc = scenarios()
    survived, skipped = [], 0
    for program, name, rel, old, new in MUTANTS:
        if a.only not in name: continue
        f = SRC / rel; orig = f.read_text()
        if old not in orig:
            print(f"SKIP     [{program}] {name}: pattern not found"); skipped += 1; continue
        f.write_text(orig.replace(old, new, 1))
        try:
            if not build():
                print(f"NOBUILD  [{program}] {name}: does not compile"); skipped += 1; continue
            caught = []
            for sc in all_sc:
                if sc["program"] != program: continue
                out = Path(tempfile.mkdtemp(prefix="mut-")) / "out"
                _, v = run_scenario(sc, JAR, out)
                if v.returncode != 0: caught.append(sc["name"].split("/")[1])
            print(f"{'KILLED  ' if caught else 'SURVIVED'} [{program:<8}] {name:<56} caught by: {', '.join(caught) or '-'}", flush=True)
            if not caught: survived.append(f"[{program}] {name}")
        finally:
            f.write_text(orig)
    build()                                       # leave a good build behind
    run = sum(1 for m in MUTANTS if a.only in m[1]) - skipped
    print(f"\n{run - len(survived)} killed, {len(survived)} survived, {skipped} skipped")
    for s in survived: print("  coverage gap -> no scenario exercises:", s)
    sys.exit(1 if survived or skipped else 0)


if __name__ == "__main__":
    main()
