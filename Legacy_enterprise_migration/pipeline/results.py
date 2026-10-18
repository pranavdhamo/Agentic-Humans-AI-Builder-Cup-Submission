#!/usr/bin/env python3
"""Aggregate every pipeline run (runs/ and runs_archive/) into a results table: pipeline/RESULTS.md.
  results.py            writes RESULTS.md and prints it"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

def rows():
    out = []
    for d in sorted([*(HERE / "runs").glob("*"), *(HERE / "runs_archive").glob("*")]):
        rp = d / "report.json"
        if not rp.exists(): continue
        r = json.loads(rp.read_text()); its = r["iterations"]
        if r["provider"] == "mock": continue
        first, last = its[0], its[-1]
        tot = lambda k: sum(i.get(k, 0) for i in its)
        out.append(dict(
            run=d.name[:15], program=r["program"], model=r["model"], mode=r["mode"],
            suite=f"{last.get('scenarios_total', first.get('scenarios_total', '?'))} scenarios",
            first=f"{first.get('records_matched', 0)}/{first.get('records_total', '?')}" if first.get("build") else "build failed",
            repairs=len(its) - 1, verdict=r["verdict"],
            final=f"{last.get('records_matched', 0)}/{last.get('records_total', '?')}" if last.get("build") else "build failed",
            tin=tot("prompt_tokens"), tout=tot("output_tokens"), mins=round(tot("llm_seconds") / 60, 1)))
    return out

def main():
    R = rows()
    head = "| Run | Program | Model | Mode | Test suite | First attempt (records identical) | Repairs | Final | Verdict | Tokens in / out | LLM time |\n|---|---|---|---|---|---|---|---|---|---|---|\n"
    body = "".join(f"| {r['run']} | {r['program']} | {r['model']} | {r['mode']} | {r['suite']} | {r['first']} | {r['repairs']} | {r['final']} | **{r['verdict']}** | {r['tin']:,} / {r['tout']:,} | {r['mins']} min |\n" for r in R)
    note = ("\nRecords identical = records whose every field matches what the REAL COBOL produced, summed over all scenarios. "
            "The test suite grew between runs (a stronger scenario was added after the first run exposed a shortcut), so compare "
            "rows with the same suite size. The 2-scenario posttran PASS (20261018-003010) was a false pass: it hard-coded a zero filler, and "
            "re-scoring that code on the later hidden-state scenario FAILS (5/55 category records wrong). Single runs at low temperature: indicative, not statistics. Token counts are as reported by the API.\n")
    text = "# Migration pipeline results\n\n" + head + body + note
    (HERE / "RESULTS.md").write_text(text); print(text)

if __name__ == "__main__":
    main()
