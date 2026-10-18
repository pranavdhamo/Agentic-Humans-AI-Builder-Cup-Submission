"""Background jobs with an append-only event log that the API streams over SSE.

One job runs at a time: the toolchain shares a Maven target directory and the golden files, so parallel runs would
corrupt each other. Every job is either a subprocess (maven, migrate.py, mutation_check.py) or an in-process loop
(the verifier), and both report through the same event stream.

migrate.py talks to the studio through plain stdout lines:
  @@STEP {...}        progress (llm / build / verify / decision) -> "step" events, drives the migration tree
  @@GATE {...}        the run is paused for a human           -> "gate" event; answered via Job.answer_gate()
  @@GATE_DONE {...}   the human decision was received         -> "gate_done" event
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import settings

ATTEMPT_RE = re.compile(
    r"^(?P<label>generated|repair \d+)\s+(?:(?P<ok>build OK)\s+scenarios (?P<sp>\d+)/(?P<st>\d+)\s+records (?P<rm>\d+)/(?P<rt>\d+)"
    r"\s+tokens in/out (?P<ti>\d+)/(?P<to>\d+)|(?P<bad>BUILD FAILED)(?:\s+tokens in/out (?P<ti2>\d+)/(?P<to2>\d+))?)"
)
REPORT_RE = re.compile(r"Report:\s*(?P<path>.+report\.json)")
KINDS = ("verify", "migrate", "build", "mutation")


class BusyError(RuntimeError):
    pass


@dataclass
class Job:
    id: str
    kind: str
    params: dict[str, Any]
    owner: dict[str, Any] = field(default_factory=dict)  # {project_id, user_id, user_name}
    status: str = "queued"  # queued | running | passed | failed | error | cancelled
    created: float = field(default_factory=time.time)
    started: float | None = None
    finished: float | None = None
    result: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    cancel_flag: threading.Event = field(default_factory=threading.Event)
    proc: subprocess.Popen | None = None
    env: dict[str, str] = field(default_factory=dict)
    gate_dir: Path | None = None
    pending_gate: dict[str, Any] | None = None

    def emit(self, type_: str, **data: Any) -> None:
        self.events.append({"seq": len(self.events), "ts": time.time(), "type": type_, **data})

    def log(self, line: str) -> None:
        self.emit("log", line=line.rstrip("\n"))

    def answer_gate(self, gate_id: str, action: str, hint: str, by: str) -> None:
        if self.gate_dir is None or not self.pending_gate or self.pending_gate["id"] != gate_id:
            raise KeyError("no such pending gate")
        (self.gate_dir / f"response-{gate_id}.json").write_text(json.dumps({"action": action, "hint": hint[:4000], "by": by}))

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id, "kind": self.kind, "params": self.params, "owner": self.owner, "status": self.status,
            "created": self.created, "started": self.started, "finished": self.finished, "result": self.result,
            "event_count": len(self.events), "pending_gate": self.pending_gate,
        }


def tool_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["SRC"] = str(settings.carddemo_src)
    env.update(extra or {})
    return env


def _kill_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    else:
        proc.terminate()


def _stream(job: Job, cmd: list[str], on_line: Callable[[str], bool | None] | None = None) -> int:
    """Run `cmd`, mirror its output into log events. `on_line` returns True to swallow a protocol line."""
    job.log("$ " + " ".join(cmd))
    proc = subprocess.Popen(
        cmd, cwd=settings.root, env=tool_env(job.env), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
    )
    job.proc = proc
    assert proc.stdout is not None
    for line in proc.stdout:
        text = line.strip()
        if not (on_line and on_line(text) is True):
            job.log(line)
        if job.cancel_flag.is_set():
            _kill_tree(proc)
    proc.wait()
    job.proc = None
    return proc.returncode


def _mvn() -> str:
    return shutil.which("mvn") or "mvn"


# --------------------------------------------------------------------------- runners


def run_build(job: Job) -> None:
    rc = _stream(job, [_mvn(), "-B", "-q", "-f", "migrated/carddemo-batch/pom.xml", "package"])
    job.result = {"jar_built": settings.jar.exists(), "return_code": rc}
    job.status = "passed" if rc == 0 else "failed"


def run_verify(job: Job) -> None:
    sys.path.insert(0, str(settings.root / "verifier"))
    from check_all import run_scenario  # noqa: PLC0415
    from scenarios import scenarios  # noqa: PLC0415

    if not settings.jar.exists():
        job.log("jar not found, building the Java project first")
        if _stream(job, [_mvn(), "-B", "-q", "-DskipTests", "-f", "migrated/carddemo-batch/pom.xml", "package"]) != 0:
            job.status, job.result = "error", {"error": "maven build failed"}
            return

    only = (job.params.get("only") or "").strip()
    todo = [s for s in scenarios() if only in s["name"]]
    job.emit("plan", scenarios=[s["name"] for s in todo])
    passed = rec_ok = rec_all = 0

    for sc in todo:
        if job.cancel_flag.is_set():
            job.status = "cancelled"
            return
        job.emit("scenario_start", name=sc["name"])
        out = Path(tempfile.mkdtemp(prefix="studio-")) / "out"
        t0 = time.time()
        proc, ver = run_scenario(sc, settings.jar, out)
        report: dict[str, Any] = {}
        jp = Path(str(out) + ".json")
        if jp.exists():
            report = json.loads(jp.read_text(errors="replace"))
        ok = ver.returncode == 0
        passed += ok
        rec_ok += report.get("records_matched", 0)
        rec_all += report.get("records_total", 0)
        job.emit(
            "scenario", name=sc["name"], program=sc["program"], passed=ok, seconds=round(time.time() - t0, 2),
            records_matched=report.get("records_matched", 0), records_total=report.get("records_total", 0),
            report=report, crashed=not (out / "rc.txt").exists(),
            console=(proc.stdout + proc.stderr)[-400:] if not ok else "",
        )
        shutil.rmtree(out.parent, ignore_errors=True)
    job.result = {"scenarios_passed": passed, "scenarios_total": len(todo), "records_matched": rec_ok, "records_total": rec_all}
    job.status = "passed" if passed == len(todo) else "failed"


def _protocol(job: Job, line: str) -> bool:
    """Handle @@STEP / @@GATE / @@GATE_DONE lines; True means the line was consumed."""
    for prefix, kind in (("@@STEP ", "step"), ("@@GATE_DONE ", "gate_done"), ("@@GATE ", "gate")):
        if line.startswith(prefix):
            try:
                data = json.loads(line[len(prefix):])
            except json.JSONDecodeError:
                return True
            if kind == "gate":
                job.pending_gate = data
            elif kind == "gate_done":
                job.pending_gate = None
            job.emit(kind, **data)
            return True
    return False


def run_migrate(job: Job) -> None:
    p = job.params
    cmd = [sys.executable, "pipeline/migrate.py", "--program", p["program"], "--provider", p["provider"],
           "--mode", p["mode"], "--max-repairs", str(p["max_repairs"])]
    if p.get("model"):
        cmd += ["--model", p["model"]]
    if p.get("gates"):
        job.gate_dir = Path(tempfile.mkdtemp(prefix="gates-"))
        job.env["STUDIO_GATE_DIR"] = str(job.gate_dir)
        cmd += ["--gates", ",".join(p["gates"]), "--gate-timeout", str(p.get("gate_timeout", 1200))]
    attempts: list[dict[str, Any]] = []
    report_path: list[str] = []

    def on_line(line: str) -> bool | None:
        if _protocol(job, line):
            return True
        m = ATTEMPT_RE.match(line)
        if m:
            g = m.groupdict()
            built = bool(g["ok"])
            a = {
                "label": g["label"], "build": built,
                "scenarios_passed": int(g["sp"]) if built else 0, "scenarios_total": int(g["st"]) if built else 0,
                "records_matched": int(g["rm"]) if built else 0, "records_total": int(g["rt"]) if built else 0,
                "prompt_tokens": int(g["ti"] or g["ti2"] or 0), "output_tokens": int(g["to"] or g["to2"] or 0),
            }
            attempts.append(a)
            job.emit("attempt", **a)
        r = REPORT_RE.search(line)
        if r:
            report_path.append(r.group("path").strip())
        return None

    if p["provider"] == "gemini" and not (job.env.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        job.status, job.result = "error", {"error": "no Gemini API key configured (Admin > AI Providers)"}
        job.log(job.result["error"])
        return
    if not settings.carddemo_src.exists():
        job.status = "error"
        job.result = {"error": f"CardDemo source not found at {settings.carddemo_src}. Set SRC (see BOOTUP.md level 2)."}
        job.log(job.result["error"])
        return
    job.log("model call in progress; a real Gemini run takes 3-7 minutes" if p["provider"] == "gemini" else "mock provider (scripted)")
    rc = _stream(job, cmd, on_line)
    run_name = Path(report_path[-1]).parent.name if report_path else None
    stopped = False
    if run_name:
        try:
            stopped = bool(json.loads((settings.runs_dir / run_name / "report.json").read_text()).get("stopped_by_reviewer"))
        except (OSError, json.JSONDecodeError):
            pass
    job.result = {"return_code": rc, "run": f"runs:{run_name}" if run_name else None, "attempts": attempts, "stopped_by_reviewer": stopped}
    job.status = ("passed" if rc == 0 else "failed") if run_name else "error"
    if not run_name:
        job.result["error"] = "migration did not produce a report (see log)"
    if job.gate_dir:
        shutil.rmtree(job.gate_dir, ignore_errors=True)


def run_mutation(job: Job) -> None:
    rc = _stream(job, [sys.executable, "verifier/mutation_check.py"])
    job.result = {"return_code": rc}
    job.status = "passed" if rc == 0 else "failed"


RUNNERS: dict[str, Callable[[Job], None]] = {
    "build": run_build, "verify": run_verify, "migrate": run_migrate, "mutation": run_mutation,
}


# --------------------------------------------------------------------------- manager


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self.on_finish: Callable[[Job], None] | None = None

    def start(self, kind: str, params: dict[str, Any], owner: dict[str, Any] | None = None, env: dict[str, str] | None = None) -> Job:
        with self._lock:
            if any(j.status in ("queued", "running") for j in self._jobs.values()):
                raise BusyError("another job is running")
            job = Job(id=uuid.uuid4().hex[:10], kind=kind, params=params, owner=owner or {}, env=env or {})
            self._jobs[job.id] = job
        threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return job

    def _run(self, job: Job) -> None:
        job.status, job.started = "running", time.time()
        job.emit("status", status="running")
        try:
            RUNNERS[job.kind](job)
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI as an error job
            job.status, job.result = "error", {"error": f"{type(exc).__name__}: {exc}"}
            job.log(job.result["error"])
        if job.cancel_flag.is_set() and job.status != "passed":
            job.status = "cancelled"
        job.finished = time.time()
        job.env.pop("GEMINI_API_KEY", None)  # never keep the key around after the run
        if self.on_finish:
            try:
                self.on_finish(job)
            except Exception:  # noqa: BLE001
                job.log("warning: could not record usage for this job")
        job.emit("status", status=job.status, result=job.result)

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        return sorted(self._jobs.values(), key=lambda j: j.created, reverse=True)

    def cancel(self, job: Job) -> None:
        job.cancel_flag.set()
        if job.proc is not None:
            _kill_tree(job.proc)


manager = JobManager()
