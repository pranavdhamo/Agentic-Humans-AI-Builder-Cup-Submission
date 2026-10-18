"""Migration run history: curated results (pipeline/results) and fresh runs (pipeline/runs)."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import settings

SOURCES = {"results": lambda: settings.results_dir, "runs": lambda: settings.runs_dir}
NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _dir(source: str, name: str) -> Path:
    if source not in SOURCES or not NAME_RE.match(name):
        raise KeyError("bad run id")
    d = SOURCES[source]() / name
    if not (d / "report.json").exists():
        raise KeyError("run not found")
    return d


def _created(name: str) -> str | None:
    m = re.match(r"(\d{8})-(\d{6})", name)
    return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").isoformat() if m else None


def _summary(source: str, d: Path) -> dict[str, Any]:
    rep = json.loads((d / "report.json").read_text(errors="replace"))
    its = rep.get("iterations", [])
    built = [i for i in its if i.get("build")]
    first = built[0] if built else {}
    last = its[-1] if its else {}
    return {
        "id": f"{source}:{d.name}", "source": source, "name": d.name, "created": _created(d.name),
        "program": rep.get("program"), "provider": rep.get("provider"), "model": rep.get("model"),
        "mode": rep.get("mode"), "verdict": rep.get("verdict"), "attempts": len(its), "repairs": max(0, len(its) - 1),
        "first_records_matched": first.get("records_matched"), "records_total": last.get("records_total") or first.get("records_total"),
        "final_records_matched": last.get("records_matched"),
        "prompt_tokens": rep.get("total_prompt_tokens", 0), "output_tokens": rep.get("total_output_tokens", 0),
        "llm_seconds": round(sum(i.get("llm_seconds", 0) for i in its), 1),
        "is_mock": rep.get("provider") == "mock",
    }


def list_runs() -> list[dict[str, Any]]:
    out = []
    for source, getter in SOURCES.items():
        base = getter()
        if base.exists():
            out += [_summary(source, d) for d in base.iterdir() if (d / "report.json").exists()]
    return sorted(out, key=lambda r: r["created"] or "", reverse=True)


def run_detail(source: str, name: str) -> dict[str, Any]:
    d = _dir(source, name)
    rep = json.loads((d / "report.json").read_text(errors="replace"))
    rules = json.loads((d / "rules.json").read_text(errors="replace")) if (d / "rules.json").exists() else None
    iters = sorted(p for p in d.glob("iter*") if p.is_dir())
    return {"summary": _summary(source, d), "report": rep, "rules": rules,
            "iterations_available": [int(p.name[4:]) for p in iters]}


def iteration_detail(source: str, name: str, n: int) -> dict[str, Any]:
    d = _dir(source, name) / f"iter{n}"
    if not d.is_dir():
        raise KeyError("iteration artifacts not stored for this run")

    def read(p: str) -> str:
        f = d / p
        return f.read_text(errors="replace")[:300_000] if f.exists() else ""

    resp = json.loads(read("response.json") or "{}")
    return {"n": n, "prompt": read("prompt.txt"), "feedback": read("feedback.txt"),
            "notes": resp.get("notes", ""), "files": resp.get("files", {})}
