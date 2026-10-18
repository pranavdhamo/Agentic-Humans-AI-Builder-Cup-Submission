"""Read-only endpoints: environment, catalog, golden data, code and run history."""
from __future__ import annotations

import os
import shutil
import subprocess

from fastapi import APIRouter, Depends, HTTPException, Query

from app import __version__, db
from app.config import settings
from app.deps import current_user, project_for
from app.services import authz, catalog, runs

public = APIRouter(prefix="/api")
router = APIRouter(prefix="/api", dependencies=[Depends(current_user)])


def _version(cmd: list[str]) -> str | None:
    exe = shutil.which(cmd[0])
    if not exe:
        return None
    try:
        r = subprocess.run([exe, *cmd[1:]], capture_output=True, text=True, timeout=15)
        return ((r.stdout or r.stderr).strip().splitlines() or [""])[0]
    except Exception:  # noqa: BLE001
        return None


@public.get("/health")
def health() -> dict:
    return {"status": "ok", "service": settings.app_name, "version": __version__}


@router.get("/environment")
def environment() -> dict:
    """What this machine can run. Gemini key is reported as a boolean only; its value is never exposed."""
    java, mvn = _version(["java", "-version"]), _version(["mvn", "-v"])
    return {
        "checks": [
            {"id": "java", "label": "JDK 21+", "ok": java is not None, "detail": java or "java not on PATH"},
            {"id": "maven", "label": "Maven", "ok": mvn is not None, "detail": mvn or "mvn not on PATH"},
            {"id": "jar", "label": "Java project built", "ok": settings.jar.exists(),
             "detail": "jar present" if settings.jar.exists() else "run the Build job (or the Verifier will build it)"},
            {"id": "carddemo", "label": "CardDemo COBOL source", "ok": settings.carddemo_src.exists(),
             "detail": str(settings.carddemo_src) if settings.carddemo_src.exists() else "needed for migrations; set SRC (BOOTUP.md level 2)"},
            {"id": "gemini", "label": "Gemini API key", "ok": authz.gemini_key_available(),
             "detail": "configured" if authz.gemini_key_available() else "optional; an admin can add a key under Admin > AI Providers"},
        ],
        "cwd": os.fspath(settings.root),
    }


@router.get("/programs")
def programs() -> list[dict]:
    return [{"id": k, **v} for k, v in catalog.PROGRAMS.items()]


@router.get("/scenarios")
def scenarios() -> list[dict]:
    return catalog.list_scenarios()


@router.get("/golden")
def golden(scenario: str, artifact: str, offset: int = Query(0, ge=0), limit: int = Query(40, ge=1, le=200)) -> dict:
    try:
        return catalog.golden_records(scenario, artifact, offset, limit)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(404, f"golden file missing: {e}") from e


@router.get("/code/{program}/java")
def reference_java(program: str) -> list[dict]:
    if program not in catalog.PROGRAMS:
        raise HTTPException(404, "unknown program")
    return catalog.reference_java(program)


@router.get("/code/{program}/cobol")
def cobol(program: str) -> dict:
    if program not in catalog.PROGRAMS:
        raise HTTPException(404, "unknown program")
    return catalog.cobol_source(program)


def _run_allowed(user: dict, source: str, name: str) -> None:
    """Curated results are visible to everyone; fresh runs only to members of the project that owns them (admins see all)."""
    if source == "results" or user["role"] == "project_admin":
        return
    meta = db.q("SELECT project_id FROM runs_meta WHERE run_name=?", (name,), one=True)
    if not meta or not any(p["id"] == meta["project_id"] for p in db.user_projects(user)):
        raise HTTPException(404, "run not found")


@router.get("/runs")
def list_runs(project_id: str | None = None, user: dict = Depends(current_user)) -> list[dict]:
    if project_id:
        project_for(user, project_id)
    allowed = {p["id"] for p in db.user_projects(user)}
    meta = {m["run_name"]: m for m in db.q("SELECT run_name,project_id,user_id FROM runs_meta")}
    names = {u["id"]: u["name"] for u in db.q("SELECT id,name FROM users")}
    out = []
    for r in runs.list_runs():
        if r["source"] == "runs":
            m = meta.get(r["name"])
            visible = (m and m["project_id"] in allowed) or (user["role"] == "project_admin")
            if not visible or (project_id and (not m or m["project_id"] != project_id)):
                continue
            r["project_id"] = m["project_id"] if m else None
            r["started_by"] = names.get(m["user_id"]) if m else None
        out.append(r)
    return out


@router.get("/runs/{source}/{name}")
def run_detail(source: str, name: str, user: dict = Depends(current_user)) -> dict:
    _run_allowed(user, source, name)
    try:
        return runs.run_detail(source, name)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


@router.get("/runs/{source}/{name}/iterations/{n}")
def iteration(source: str, name: str, n: int, user: dict = Depends(current_user)) -> dict:
    _run_allowed(user, source, name)
    try:
        return runs.iteration_detail(source, name, n)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
