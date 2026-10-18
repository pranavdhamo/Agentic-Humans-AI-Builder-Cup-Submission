"""Scripted answers for MockProvider: the reference port with injected mistakes that disappear, one group per round.
Used ONLY to test the loop mechanics offline. The mistakes are the same plausible ones the mutation check uses."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "verifier"))
from mutation_check import MUTANTS          # noqa: E402

BASE = "src/main/java/com/agentichumans/carddemo"
PKG = {"posttran": "posttran", "intcalc": "intcalc"}
PLAN = {
    "posttran": [["expiry check dropped", "debit/credit branch swapped", "FILLER ignores carried-over COBOL state", "invalid-card reject code 101 instead of 100"],
                 ["expiry check dropped", "FILLER ignores carried-over COBOL state"],
                 ["FILLER ignores carried-over COBOL state"], []],
    "intcalc": [["interest rounds HALF_UP instead of truncating", "last account settled (legacy bug 'fixed')", "cycle credit not reset", "missing account skipped instead of abend"],
                ["interest rounds HALF_UP instead of truncating", "missing account skipped instead of abend"],
                ["missing account skipped instead of abend"], []],
}


def versions(program):
    pkg = PKG[program]
    ref = {f"{BASE}/{pkg}/{p.name}": p.read_text()
           for p in sorted((ROOT / f"migrated/carddemo-batch/{BASE}/{pkg}").glob("*.java"))}
    by_name = {m[1]: m for m in MUTANTS if m[0] == program}

    def make(names):
        def build():
            files = dict(ref)
            for n in names:
                _, _, rel, old, new = by_name[n]
                key = f"{BASE}/{rel}"
                assert key in files and old in files[key], f"mock mutant not applicable: {n}"
                files[key] = files[key].replace(old, new, 1)
            return files
        return build
    return [make(names) for names in PLAN[program]]
