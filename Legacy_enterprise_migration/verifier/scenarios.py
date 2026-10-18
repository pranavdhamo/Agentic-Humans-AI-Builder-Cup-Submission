"""Registry of every scenario: which migrated program to run, with what inputs, and where the COBOL golden output is."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORACLE = ROOT / "oracle"
JAR = ROOT / "migrated/carddemo-batch/target/carddemo-batch-0.1.0.jar"

def scenarios():
    S = []
    sample_in = ORACLE / "golden/posttran/input"
    S.append(dict(name="posttran/sample", program="posttran", golden=ORACLE / "golden/posttran",
                  args=[f"--carddemo.input-dir={sample_in}", f"--carddemo.dailytran={ORACLE / 'golden/posttran/DALYTRAN.input'}"]))
    S.append(dict(name="posttran/edge", program="posttran", golden=ORACLE / "golden/edge",
                  args=[f"--carddemo.input-dir={sample_in}", f"--carddemo.dailytran={ORACLE / 'scenarios/edge/DALYTRAN.input'}"]))
    hs = ORACLE / "golden/hidden-state"
    S.append(dict(name="posttran/hidden-state", program="posttran", golden=hs,
                  args=[f"--carddemo.input-dir={hs / 'input'}", f"--carddemo.dailytran={ORACLE / 'scenarios/hidden-state/DALYTRAN.input'}"]))
    S.append(dict(name="intcalc/sample", program="intcalc", golden=ORACLE / "golden/posttran/intcalc",
                  args=[f"--carddemo.state-dir={ORACLE / 'golden/posttran'}", f"--carddemo.input-dir={sample_in}",
                        "--carddemo.int-date=2022-07-01"]))
    for s in ["interest-edge", "interest-abend-account", "interest-abend-xref", "interest-abend-rate"]:
        g = ORACLE / "golden" / s
        S.append(dict(name=f"intcalc/{s}", program="intcalc", golden=g / "intcalc",
                      args=[f"--carddemo.state-dir={g}", f"--carddemo.input-dir={g / 'input'}", "--carddemo.int-date=2022-07-01"]))
    return S
