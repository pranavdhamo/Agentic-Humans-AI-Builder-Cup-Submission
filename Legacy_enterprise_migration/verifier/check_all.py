#!/usr/bin/env python3
"""Run every migrated program on every scenario and verify against the COBOL golden output.
  check_all.py [--jar path] [--only substring]      exit 0 = all scenarios PASS"""
import argparse, os, shutil, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from scenarios import scenarios, JAR, ROOT


def java_env():
    """Environment for java/mvn: honour JAVA_HOME; on macOS fall back to Homebrew's keg-only OpenJDK; else use PATH as is."""
    env = dict(os.environ)
    jh = env.get("JAVA_HOME") or ("/opt/homebrew/opt/openjdk" if Path("/opt/homebrew/opt/openjdk/bin/java").exists() else "")
    if jh:
        env["JAVA_HOME"] = jh
        env["PATH"] = jh + "/bin:" + env["PATH"]
    return env


def run_scenario(sc, jar, out):
    env = java_env()
    p = subprocess.run(["java", "-jar", str(jar), f"--carddemo.job={sc['program']}", f"--carddemo.output-dir={out}", *sc["args"]],
                       capture_output=True, text=True, env=env)
    v = subprocess.run([sys.executable, str(ROOT / "verifier/verify.py"), "--program", sc["program"], "--golden", str(sc["golden"]),
                        "--candidate", str(out), "--json", str(out) + ".json"], capture_output=True, text=True)
    return p, v

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--jar", default=str(JAR)); ap.add_argument("--only", default="")
    a = ap.parse_args()
    failed = 0
    print(f"{'scenario':<34}{'records':>14}   verdict")
    for sc in scenarios():
        if a.only not in sc["name"]: continue
        out = Path(tempfile.mkdtemp(prefix="cd-")) / "out"
        p, v = run_scenario(sc, a.jar, out)
        last = v.stdout.strip().splitlines()[-1] if v.stdout.strip() else v.stderr[-200:]
        rec = last.split("records ")[1].split(" ")[0] if "records " in last else "-"
        verdict = "PASS" if v.returncode == 0 else "FAIL"
        failed += verdict == "FAIL"
        print(f"{sc['name']:<34}{rec:>14}   {verdict}")
        if verdict == "FAIL":
            for line in v.stdout.strip().splitlines()[:-1]:
                if "IDENTICAL" not in line: print("   ", line)
            if not (out / "rc.txt").exists(): print("    (no output produced)", p.stdout[-300:], p.stderr[-300:])
        shutil.rmtree(out.parent, ignore_errors=True)
    print(f"\n{'ALL SCENARIOS PASS' if not failed else str(failed) + ' scenario(s) FAIL'}")
    sys.exit(1 if failed else 0)

if __name__ == "__main__":
    main()
