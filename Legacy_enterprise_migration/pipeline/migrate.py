#!/usr/bin/env python3
"""Agentic migration loop: COBOL -> Java, proven against the real COBOL.

  generate  Gemini ports a COBOL program (given the source, copybooks, shared COBOL-semantics library, output contract)
  build     Maven compiles it                                  -> compiler errors are fed back
  verify    runs it on every scenario and diffs every output record against what the REAL COBOL produced
  repair    field-level mismatches (with the business case each record exercises) go back to the model; repeat

The reference port in migrated/ is NEVER shown to the model: the workspace is a copy with that program's package removed.

  migrate.py --program posttran|intcalc [--provider gemini|mock] [--mode guided|naive] [--max-repairs 4] [--model NAME]
Needs: JDK 21+ and Maven, a CardDemo checkout (SRC, default ~/carddemo-env-local/carddemo/app), and for --provider gemini
the GEMINI_API_KEY environment variable.
"""
import argparse, datetime, json, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path[:0] = [str(ROOT / "verifier"), str(HERE)]
from scenarios import scenarios, ORACLE                      # noqa: E402
from check_all import run_scenario, java_env                 # noqa: E402
import llm, prompts                                          # noqa: E402

BASE = "src/main/java/com/agentichumans/carddemo"
ENV = java_env()

PROGRAMS = {
    "posttran": dict(
        cobol="CBTRN02C", pkg="posttran",
        properties="""\
  carddemo.input-dir   directory with LINE-SEQUENTIAL initial files: cardxref.txt (50-byte records), acctdata.txt (300), tcatbal.txt (50).
                       Lines shorter than the record length are right-padded with spaces (that is how the COBOL loader treats them).
  carddemo.dailytran   the daily transaction file (fixed 350-byte records, no line breaks)
  carddemo.output-dir  where to write the outputs""",
        outputs="""\
  DALYREJS.ps    430-byte reject records (the 350-byte input record + 4-digit reason + 76-char description), in arrival order
  TRANSACT.flat  350-byte posted transactions, in ascending TRAN-ID order (indexed file read sequentially)
  ACCTDATA.flat  final 300-byte account records, ascending account id
  TCATBALF.flat  final 50-byte transaction-category-balance records, ascending key
  stdout.txt     the console lines: 'TRANSACTIONS PROCESSED :' + 9 digits and 'TRANSACTIONS REJECTED  :' + 9 digits (one per line)
  rc.txt         the COBOL RETURN-CODE and a newline"""),
    "intcalc": dict(
        cobol="CBACT04C", pkg="intcalc",
        properties="""\
  carddemo.state-dir   directory with ACCTDATA.flat (300-byte records) and TCATBALF.flat (50-byte records, key order): the state
                       after the posting program; fixed-width, no line breaks
  carddemo.input-dir   directory with LINE-SEQUENTIAL cardxref.txt (50-byte records) and discgrp.txt (50-byte records), right-padded
  carddemo.int-date    the JCL PARM: a 10-character date (YYYY-MM-DD) used as the interest-transaction id prefix
  carddemo.output-dir  where to write the outputs""",
        outputs="""\
  SYSTRAN.ps     350-byte interest transactions, in the order the COBOL WRITEs them
  ACCTDATA.flat  final 300-byte account records, ascending account id
  stdout.txt     'START OF EXECUTION OF PROGRAM CBACT04C' and 'END OF EXECUTION OF PROGRAM CBACT04C'
  rc.txt         the return code (0 normal, 16 after an abend: the CEE3ABD stand-in) and a newline"""),
}


def read(p): return Path(p).read_text(errors="replace")


# --- studio protocol: structured progress lines (@@STEP) and human-in-the-loop gates (@@GATE) -------------------------------
# Plain stdout lines, so the CLI keeps working on its own; the studio server parses them into events.
def emit(kind, **kw): print("@@STEP " + json.dumps({"kind": kind, **kw}), flush=True)


class Gates:
    """Pause the loop and wait for a human decision written by the studio (STUDIO_GATE_DIR/response-<id>.json)."""
    def __init__(self, points, timeout):
        self.points, self.timeout, self.n = set(points), timeout, 0
        self.dir = Path(os.environ["STUDIO_GATE_DIR"]) if os.environ.get("STUDIO_GATE_DIR") else None
        self.decisions = []

    def ask(self, point, iteration, summary, detail=""):
        """Returns {'action': 'approve'|'stop', 'hint': str}. No gate configured for this point -> approve silently."""
        if point not in self.points or self.dir is None:
            return {"action": "approve", "hint": ""}
        self.n += 1; gid = f"g{self.n}"
        print("@@GATE " + json.dumps({"id": gid, "point": point, "iteration": iteration, "summary": summary,
                                      "detail": detail[:4000], "timeout": self.timeout}), flush=True)
        resp = self.dir / f"response-{gid}.json"
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            if resp.exists():
                d = json.loads(resp.read_text()); d.setdefault("hint", ""); d.setdefault("action", "approve")
                self.decisions.append(dict(id=gid, point=point, iteration=iteration, **d))
                print("@@GATE_DONE " + json.dumps({"id": gid, "action": d["action"], "hint": d["hint"], "by": d.get("by")}), flush=True)
                return d
            time.sleep(0.5)
        d = {"action": "stop", "hint": "", "by": "timeout"}
        self.decisions.append(dict(id=gid, point=point, iteration=iteration, **d))
        print("@@GATE_DONE " + json.dumps({"id": gid, "action": "stop", "hint": "", "by": "timeout"}), flush=True)
        return d


def reviewer_note(hint):
    if not (hint and hint.strip()): return ""
    return ("\n\nHUMAN REVIEWER GUIDANCE (from the project's reviewers; follow it unless it conflicts with the output contract):\n"
            + hint.strip())


def cobol_inputs(program, src):
    cbl = next((src / "cbl").glob(PROGRAMS[program]["cobol"] + ".[cC][bB][lL]"))
    text = read(cbl)
    names = re.findall(r"^\s{6,7}\s*COPY\s+([A-Z0-9-]+)\s*\.", text, re.M)
    cpy = {}
    for n in names:
        f = next(iter((src / "cpy").glob(n + ".[cC][pP][yY]")), None)
        if f and n not in cpy: cpy[n] = read(f)
    return text, cpy


def library_source(project):
    out = []
    for rel in ["cobol/CobolNumeric.java", "cobol/Records.java", "cobol/FixedRecordReader.java", "cobol/RunResult.java"]:
        out.append(f"// ---- {rel}\n{read(Path(project) / BASE / rel)}")
    return "\n".join(out)


def make_workspace(program, run_dir):
    proj = run_dir / "project"
    shutil.copytree(ROOT / "migrated/carddemo-batch", proj, ignore=shutil.ignore_patterns("target", "test"))
    shutil.rmtree(proj / BASE / PROGRAMS[program]["pkg"])       # the reference port must not be visible
    (proj / BASE / PROGRAMS[program]["pkg"]).mkdir()
    return proj


def write_files(proj, program, files):
    pkg = PROGRAMS[program]["pkg"]; prefix = f"{BASE}/{pkg}/"
    for rel, content in files.items():
        if not rel.startswith(prefix) or not rel.endswith(".java") or ".." in rel:
            raise ValueError(f"file outside the allowed package: {rel}")
    d = proj / BASE / pkg
    shutil.rmtree(d); d.mkdir()
    for rel, content in files.items():
        p = proj / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(content)


def build(proj):
    r = subprocess.run([shutil.which("mvn") or "mvn", "-q", "-DskipTests", "package"], cwd=proj, env=ENV, capture_output=True, text=True)
    errs = [l for l in (r.stdout + r.stderr).splitlines() if "ERROR" in l and (".java" in l or "symbol" in l or "location" in l)]
    return r.returncode == 0, "\n".join(errs[:40]) or (r.stdout + r.stderr)[-1500:]


def labels_for(sc):
    n = sc["name"].split("/")[1]
    for p in [ORACLE / "scenarios" / n / "cases.json"]:
        if p.exists():
            raw = json.loads(read(p))
            return {k: (v["label"] if isinstance(v, dict) else v) for k, v in raw.items()}
    return {}


def verify_all(program, jar, run_dir, it):
    results = []
    for sc in scenarios():
        if sc["program"] != program: continue
        out = run_dir / f"iter{it}" / "out" / sc["name"].replace("/", "_")
        out.parent.mkdir(parents=True, exist_ok=True)
        p, v = run_scenario(sc, jar, out)
        rep = {}
        jp = Path(str(out) + ".json")
        if jp.exists(): rep = json.loads(read(jp))
        results.append(dict(scenario=sc["name"], passed=v.returncode == 0, report=rep, labels=labels_for(sc),
                            crashed=not (out / "rc.txt").exists(), stderr=(p.stdout + p.stderr)[-600:]))
    return results


def failure_text(build_ok, build_err, results, max_per_artifact=6):
    if not build_ok:
        return "THE CODE DID NOT COMPILE. Compiler output:\n" + build_err
    lines = []
    for r in results:
        if r["passed"]: lines.append(f"[PASS] {r['scenario']}"); continue
        lines.append(f"[FAIL] {r['scenario']}")
        if r["crashed"]: lines.append("   the job produced no output; console tail: " + r["stderr"].replace("\n", " | ")); continue
        rep = r["report"]
        if not rep.get("return_code_matches", True): lines.append("   return code differs from the COBOL run")
        if not rep.get("counters_match", True): lines.append("   console counters differ from the COBOL run")
        for a in rep.get("artifacts", []):
            if a["status"] == "IDENTICAL": continue
            lines.append(f"   {a['artifact']}: {a['matched']}/{a['golden_records']} records identical; {a.get('different', 0)} differ, "
                         f"{a.get('missing', 0)} missing, {a.get('extra', 0)} extra, record order "
                         f"{'matches' if a.get('order_matches', True) else 'DIFFERS'} ({a.get('candidate_records')} produced)")
            for m in a["mismatches"][:max_per_artifact]:
                label = r["labels"].get(m.get("key") or "", "")
                head = f"     key {m['key']}" + (f"  <{label}>" if label else "")
                if "problem" in m: lines.append(head + f": {m['problem']}"); continue
                lines.append(head + ": " + "; ".join(f"{d['field']} expected {d['expected']!r} got {d['actual']!r}" for d in m["diffs"][:4]))
    return "\n".join(lines)


def summarize(results):
    recs = [(r["report"].get("records_matched", 0), r["report"].get("records_total", 0)) for r in results]
    return dict(scenarios_passed=sum(r["passed"] for r in results), scenarios_total=len(results),
                records_matched=sum(a for a, _ in recs), records_total=sum(b for _, b in recs))


def mock_provider(program):
    from mock_versions import versions
    return llm.MockProvider(versions(program))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--program", required=True, choices=PROGRAMS)
    ap.add_argument("--provider", default="gemini", choices=["gemini", "mock"])
    ap.add_argument("--mode", default="guided", choices=["guided", "naive"], help="guided adds the generic COBOL-semantics primer")
    ap.add_argument("--max-repairs", type=int, default=4)
    ap.add_argument("--model", default=None)
    ap.add_argument("--gates", default="", help="comma list of human review points: generate,repair (needs STUDIO_GATE_DIR)")
    ap.add_argument("--gate-timeout", type=int, default=1200, help="seconds to wait for a reviewer before stopping")
    a = ap.parse_args()
    gates = Gates([g for g in a.gates.split(",") if g], a.gate_timeout)

    src = Path(os.environ.get("SRC", Path.home() / "carddemo-env-local/carddemo/app"))
    if not src.exists(): sys.exit(f"CardDemo source not found at {src} (set SRC)")
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    provider = mock_provider(a.program) if a.provider == "mock" else llm.GeminiProvider(a.model)
    run_dir = HERE / "runs" / f"{stamp}-{a.program}-{provider.model}-{a.mode}"; run_dir.mkdir(parents=True)
    proj = make_workspace(a.program, run_dir)
    P = PROGRAMS[a.program]
    cobol, copybooks = cobol_inputs(a.program, src)
    contract = prompts.CONTRACT.format(pkg=P["pkg"], properties=P["properties"], outputs=P["outputs"])
    primer = prompts.PRIMER if a.mode == "guided" else ""
    lib = library_source(proj)
    print(f"run: {run_dir.name}   model: {provider.model}   scenarios: {sum(1 for s in scenarios() if s['program'] == a.program)}")
    if a.provider == "mock": print("NOTE: MOCK provider = scripted answers, not a model. It only exercises the loop mechanics.\n")

    history, files, failures, stopped = [], None, "", False
    for it in range(a.max_repairs + 1):
        if it == 0:
            d = gates.ask("generate", 0, f"Review before the model ports {P['cobol']}; add guidance if you like.")
            if d["action"] == "stop": stopped = True; break
            primer_run = primer + reviewer_note(d["hint"])
        else:
            d = gates.ask("repair", it, f"Attempt {it - 1} did not match the COBOL. Approve a repair, add a hint, or stop.", failures)
            if d["action"] == "stop": stopped = True; break
            failures += reviewer_note(d["hint"])
        if it == 0:
            prompt = prompts.GENERATE.format(contract=contract, primer=primer_run, program_name=P["cobol"], cobol_file=P["cobol"] + ".cbl",
                                             cobol=cobol, copybooks="\n".join(f"--- {k}\n{v}" for k, v in copybooks.items()), library=lib)
        else:
            current = "\n".join(f"// ---- {k}\n{v}" for k, v in files.items())
            prompt = prompts.REPAIR.format(contract=contract, primer=primer, program_name=P["cobol"], cobol=cobol,
                                           current=current, failures=failures, iteration=it - 1)
        (run_dir / f"iter{it}").mkdir(exist_ok=True)
        (run_dir / f"iter{it}" / "prompt.txt").write_text(prompt)
        emit("llm", iteration=it, state="start")
        res = provider.complete(prompts.SYSTEM, prompt)
        emit("llm", iteration=it, state="done", prompt_tokens=res.prompt_tokens, output_tokens=res.output_tokens, seconds=round(res.seconds, 1))
        (run_dir / f"iter{it}" / "response.json").write_text(json.dumps(res.data, indent=1))
        files = res.data.get("files", {})
        if it == 0 and res.data.get("rules"): (run_dir / "rules.json").write_text(json.dumps(res.data["rules"], indent=1))
        try:
            write_files(proj, a.program, files)
        except ValueError as e:
            failures = f"REJECTED: {e}. Only files under {BASE}/{P['pkg']}/ are allowed."
            history.append(dict(iteration=it, build=False, error=str(e), prompt_tokens=res.prompt_tokens, output_tokens=res.output_tokens)); continue
        emit("build", iteration=it, state="start")
        ok, err = build(proj)
        emit("build", iteration=it, state="done", ok=ok)
        row = dict(iteration=it, build=ok, prompt_tokens=res.prompt_tokens, output_tokens=res.output_tokens, llm_seconds=round(res.seconds, 1))
        if ok:
            emit("verify", iteration=it, state="start")
            results = verify_all(a.program, proj / "target/carddemo-batch-0.1.0.jar", run_dir, it)
            row.update(summarize(results)); failures = failure_text(True, "", results)
            row["all_pass"] = row["scenarios_passed"] == row["scenarios_total"]
            emit("verify", iteration=it, state="done", passed=row["scenarios_passed"], total=row["scenarios_total"],
                 records_matched=row["records_matched"], records_total=row["records_total"])
        else:
            row["build_error"] = err[:600]; failures = failure_text(False, err, [])
        (run_dir / f"iter{it}" / "feedback.txt").write_text(failures)
        history.append(row)
        label = "generated" if it == 0 else f"repair {it}"
        if ok: print(f"{label:<10} build OK   scenarios {row['scenarios_passed']}/{row['scenarios_total']}   records {row['records_matched']}/{row['records_total']}   tokens in/out {res.prompt_tokens}/{res.output_tokens}")
        else:  print(f"{label:<10} BUILD FAILED   tokens in/out {res.prompt_tokens}/{res.output_tokens}")
        if ok and row["all_pass"]:
            emit("decision", iteration=it, outcome="pass"); break
        emit("decision", iteration=it, outcome="exhausted" if it == a.max_repairs else ("build_failed" if not ok else "mismatch"))

    final = history[-1] if history else {}
    verdict = "PASS" if final.get("all_pass") else "FAIL"
    report = dict(human=gates.decisions, stopped_by_reviewer=stopped, program=a.program, provider=a.provider, model=provider.model, mode=a.mode, verdict=verdict, iterations=history,
                  total_prompt_tokens=sum(h["prompt_tokens"] for h in history), total_output_tokens=sum(h["output_tokens"] for h in history))
    (run_dir / "report.json").write_text(json.dumps(report, indent=1))
    print(f"\nVERDICT: {verdict} after {len(history) - 1} repair(s). Report: {run_dir / 'report.json'}")
    sys.exit(0 if verdict == "PASS" else 1)


if __name__ == "__main__":
    main()
