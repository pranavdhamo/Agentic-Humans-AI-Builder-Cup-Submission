"""Projects the signed-in user belongs to, their budgets, and the per-project orchestration board."""
from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app import db
from app.deps import current_user, need, project_for
from app.jobs import BusyError, manager
from app.services import authz
from app.services.board import compile_board, default_board

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("")
def my_projects(user: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
    return db.user_projects(user)


@router.get("/{pid}/budgets")
def budgets(pid: str, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return authz.budgets(user, project_for(user, pid))


def _check_agents(user: dict[str, Any], graph: dict[str, Any]) -> list[str]:
    allowed = set(db.get_policy(user["role"])["agents"])
    return sorted({n.get("type") for n in graph.get("nodes", []) if n.get("type") not in allowed})


@router.get("/{pid}/board")
def get_board(pid: str, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    project_for(user, pid)
    row = db.q("SELECT json,updated,updated_by FROM boards WHERE project_id=?", (pid,), one=True)
    graph = json.loads(row["json"]) if row else default_board()
    return {"graph": graph, "updated": row["updated"] if row else None, "compiled": compile_board(graph),
            "editable": db.get_policy(user["role"])["can_edit_board"]}


@router.put("/{pid}/board")
def put_board(pid: str, graph: dict[str, Any], user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    project_for(user, pid)
    need(user, "can_edit_board")
    if len(json.dumps(graph)) > 200_000 or not isinstance(graph.get("nodes"), list) or not isinstance(graph.get("edges"), list):
        raise HTTPException(422, "invalid board")
    blocked = _check_agents(user, graph)
    if blocked:
        raise HTTPException(403, f"your role cannot use these agents: {', '.join(blocked)}")
    db.q("INSERT OR REPLACE INTO boards(project_id,json,updated_by,updated) VALUES(?,?,?,?)", (pid, json.dumps(graph), user["id"], time.time()), write=True)
    db.audit(user["id"], "board_saved", pid)
    return {"compiled": compile_board(graph)}


@router.post("/{pid}/board/validate")
def validate_board(pid: str, graph: dict[str, Any], user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    project_for(user, pid)
    result = compile_board(graph)
    blocked = _check_agents(user, graph)
    if blocked:
        result["ok"] = False
        result["errors"] = [*result["errors"], f"your role cannot use these agents: {', '.join(blocked)}"]
    return result


@router.post("/{pid}/board/run", status_code=202)
def run_board(pid: str, graph: dict[str, Any], user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    """Compile the drawn board and start it as a real migration job (same policy checks as the Studio)."""
    project = project_for(user, pid)
    result = validate_board(pid, graph, user)
    if not result["ok"]:
        raise HTTPException(422, "; ".join(result["errors"]))
    req = {**result["params"], "gate_timeout": 1200}
    req = authz.authorize_migration(user, project, req)
    env = {}
    if req["provider"] == "gemini" and db.provider_key():
        env["GEMINI_API_KEY"] = db.provider_key() or ""
    try:
        job = manager.start("migrate", req, owner={"project_id": pid, "user_id": user["id"], "user_name": user["name"], "via": "board"}, env=env)
    except BusyError as e:
        raise HTTPException(409, str(e)) from e
    db.audit(user["id"], "board_run", f"{pid} job {job.id}")
    return job.public()
