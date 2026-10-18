"""Read-only views over the scenario registry, golden COBOL output and source code."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from app.config import settings

PROGRAMS = {
    "posttran": {"cobol": "CBTRN02C", "title": "Daily transaction posting", "package": "posttran",
                 "summary": "Validates daily transactions, posts the good ones, rejects the rest, updates balances."},
    "intcalc": {"cobol": "CBACT04C", "title": "Monthly interest calculation", "package": "intcalc",
                "summary": "Computes interest per account and category and writes interest transactions."},
}


def _verifier():
    path = str(settings.root / "verifier")
    if path not in sys.path:
        sys.path.insert(0, path)
    import scenarios  # noqa: PLC0415
    import verify  # noqa: PLC0415

    return scenarios, verify


def _cases(sc_name: str) -> dict[str, Any]:
    folder = sc_name.split("/")[1]
    p = settings.root / "oracle/scenarios" / folder / "cases.json"
    if not p.exists():
        return {}
    raw = json.loads(p.read_text(errors="replace"))
    return {k: (v if isinstance(v, dict) else {"label": v}) for k, v in raw.items()}


def list_scenarios() -> list[dict[str, Any]]:
    scenarios, verify = _verifier()
    out = []
    for sc in scenarios.scenarios():
        cases = _cases(sc["name"])
        cats: dict[str, int] = {}
        for c in cases.values():
            cats[c.get("category", "other")] = cats.get(c.get("category", "other"), 0) + 1
        golden = Path(sc["golden"])
        out.append({
            "name": sc["name"], "program": sc["program"],
            "artifacts": [a for a in verify.PROGRAMS[sc["program"]] if (golden / a).exists()],
            "case_count": len(cases), "categories": cats,
            "sample_cases": [{"key": k, **v} for k, v in list(cases.items())[:6]],
            "return_code": (golden / "rc.txt").read_text().strip() if (golden / "rc.txt").exists() else None,
        })
    return out


def golden_records(scenario: str, artifact: str, offset: int, limit: int) -> dict[str, Any]:
    scenarios, verify = _verifier()
    sc = next((s for s in scenarios.scenarios() if s["name"] == scenario), None)
    if sc is None:
        raise KeyError("unknown scenario")
    spec = verify.PROGRAMS[sc["program"]].get(artifact)
    if spec is None:
        raise KeyError("unknown artifact")
    rl, layout, key, masked = spec
    path = Path(sc["golden"]) / artifact
    if not path.exists():
        raise FileNotFoundError(artifact)
    recs = verify.split(path.read_bytes(), rl)
    cases = _cases(scenario)
    rows = []
    for r in recs[offset: offset + limit]:
        fields = {f[0]: verify.field(r, f) for f in layout}
        k = r[key[1]: key[1] + key[2]].decode("latin-1")
        rows.append({"key": k, "label": cases.get(k, {}).get("label"), "fields": fields})
    return {"scenario": scenario, "artifact": artifact, "record_length": rl, "total": len(recs),
            "columns": [f[0] for f in layout], "masked": sorted(masked), "rows": rows}


def reference_java(program: str) -> list[dict[str, str]]:
    pkg = PROGRAMS[program]["package"]
    base = settings.root / "migrated/carddemo-batch/src/main/java/com/agentichumans/carddemo"
    files = sorted((base / pkg).glob("*.java")) + sorted((base / "cobol").glob("*.java"))
    return [{"path": str(f.relative_to(base)).replace("\\", "/"), "content": f.read_text(errors="replace")} for f in files]


def cobol_source(program: str) -> dict[str, Any]:
    src = settings.carddemo_src
    name = PROGRAMS[program]["cobol"]
    cbl = next((src / "cbl").glob(name + ".[cC][bB][lL]"), None) if (src / "cbl").exists() else None
    if cbl is None:
        return {"available": False, "program": name, "hint": f"CardDemo source not found at {src}. Set SRC (BOOTUP.md level 2).",
                "content": "", "copybooks": {}}
    text = cbl.read_text(errors="replace")
    cpy = {}
    for n in re.findall(r"^\s{6,7}\s*COPY\s+([A-Z0-9-]+)\s*\.", text, re.M):
        f = next(iter((src / "cpy").glob(n + ".[cC][pP][yY]")), None)
        if f and n not in cpy:
            cpy[n] = f.read_text(errors="replace")
    return {"available": True, "program": name, "content": text, "copybooks": cpy}
