"""Admin console API: users, teams, projects, role policies, the Gemini provider and usage. Project admin only."""
from __future__ import annotations

import json
import time
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import db, security
from app.deps import require_admin
from app.policy import MODEL_TIERS, ROLES, validate_policy

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _actor(admin: dict[str, Any]) -> str:
    return admin["id"]


# --------------------------------------------------------------------------- users


class UserIn(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+$", max_length=200)
    name: str = Field(min_length=1, max_length=100)
    role: str
    password: str = Field(min_length=8, max_length=200)


class UserPatch(BaseModel):
    name: str | None = Field(None, max_length=100)
    role: str | None = None
    active: bool | None = None
    password: str | None = Field(None, min_length=8, max_length=200)


@router.get("/users")
def list_users() -> list[dict[str, Any]]:
    rows = db.q("SELECT id,email,name,role,active,created FROM users ORDER BY created")
    for r in rows:
        r["teams"] = [t["name"] for t in db.user_teams(r["id"])]
        r["projects"] = [p["name"] for p in db.user_projects(r)]
    return rows


@router.post("/users", status_code=201)
def create_user(body: UserIn, admin: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    if body.role not in ROLES:
        raise HTTPException(422, "unknown role")
    if db.q("SELECT 1 FROM users WHERE lower(email)=lower(?)", (body.email,), one=True):
        raise HTTPException(409, "email already onboarded")
    uid = db.uid()
    db.q("INSERT INTO users(id,email,name,role,pw_hash,active,created) VALUES(?,?,?,?,?,1,?)",
         (uid, body.email.strip(), body.name.strip(), body.role, security.hash_password(body.password), time.time()), write=True)
    db.audit(_actor(admin), "user_created", f"{body.email} as {body.role}")
    return {"id": uid}


@router.patch("/users/{uid}")
def patch_user(uid: str, body: UserPatch, admin: dict[str, Any] = Depends(require_admin)) -> dict[str, bool]:
    row = db.q("SELECT * FROM users WHERE id=?", (uid,), one=True)
    if not row:
        raise HTTPException(404, "unknown user")
    if body.role is not None and body.role not in ROLES:
        raise HTTPException(422, "unknown role")
    if uid == admin["id"] and (body.active is False or (body.role and body.role != "project_admin")):
        raise HTTPException(409, "you cannot demote or deactivate yourself")
    sets, args = [], []
    for col, val in (("name", body.name), ("role", body.role), ("active", None if body.active is None else int(body.active))):
        if val is not None:
            sets.append(f"{col}=?"); args.append(val)
    if body.password:
        sets.append("pw_hash=?"); args.append(security.hash_password(body.password))
    if sets:
        db.q(f"UPDATE users SET {','.join(sets)} WHERE id=?", [*args, uid], write=True)
        db.audit(_actor(admin), "user_updated", f"{row['email']}: {', '.join(s.split('=')[0] for s in sets)}")
    return {"ok": True}


# --------------------------------------------------------------------------- teams


class TeamIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    daily_token_budget: int | None = Field(None, ge=0, le=100_000_000)
    members: list[str] = []


@router.get("/teams")
def list_teams() -> list[dict[str, Any]]:
    rows = db.q("SELECT * FROM teams ORDER BY name")
    for t in rows:
        t["members"] = [m["user_id"] for m in db.q("SELECT user_id FROM team_members WHERE team_id=?", (t["id"],))]
    return rows


def _save_team(tid: str, body: TeamIn) -> None:
    db.q("DELETE FROM team_members WHERE team_id=?", (tid,), write=True)
    for u in dict.fromkeys(body.members):
        if db.q("SELECT 1 FROM users WHERE id=?", (u,), one=True):
            db.q("INSERT INTO team_members VALUES(?,?)", (tid, u), write=True)


@router.post("/teams", status_code=201)
def create_team(body: TeamIn, admin: dict[str, Any] = Depends(require_admin)) -> dict[str, str]:
    if db.q("SELECT 1 FROM teams WHERE name=?", (body.name,), one=True):
        raise HTTPException(409, "team name exists")
    tid = db.uid()
    db.q("INSERT INTO teams(id,name,daily_token_budget) VALUES(?,?,?)", (tid, body.name, body.daily_token_budget), write=True)
    _save_team(tid, body)
    db.audit(_actor(admin), "team_created", body.name)
    return {"id": tid}


@router.put("/teams/{tid}")
def update_team(tid: str, body: TeamIn, admin: dict[str, Any] = Depends(require_admin)) -> dict[str, bool]:
    if not db.q("SELECT 1 FROM teams WHERE id=?", (tid,), one=True):
        raise HTTPException(404, "unknown team")
    db.q("UPDATE teams SET name=?, daily_token_budget=? WHERE id=?", (body.name, body.daily_token_budget, tid), write=True)
    _save_team(tid, body)
    db.audit(_actor(admin), "team_updated", body.name)
    return {"ok": True}


@router.delete("/teams/{tid}")
def delete_team(tid: str, admin: dict[str, Any] = Depends(require_admin)) -> dict[str, bool]:
    for t in ("team_members", "project_teams"):
        db.q(f"DELETE FROM {t} WHERE team_id=?", (tid,), write=True)
    db.q("DELETE FROM teams WHERE id=?", (tid,), write=True)
    db.audit(_actor(admin), "team_deleted", tid)
    return {"ok": True}


# --------------------------------------------------------------------------- projects


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field("", max_length=400)
    token_budget: int | None = Field(None, ge=0, le=1_000_000_000)
    users: list[str] = []
    teams: list[str] = []
    archived: bool = False


@router.get("/projects")
def list_projects() -> list[dict[str, Any]]:
    rows = db.q("SELECT * FROM projects ORDER BY name")
    for p in rows:
        p["users"] = [r["user_id"] for r in db.q("SELECT user_id FROM project_users WHERE project_id=?", (p["id"],))]
        p["teams"] = [r["team_id"] for r in db.q("SELECT team_id FROM project_teams WHERE project_id=?", (p["id"],))]
        p["tokens_used"] = db.tokens_since(0, project_id=p["id"])
    return rows


def _save_project(pid: str, body: ProjectIn) -> None:
    db.q("DELETE FROM project_users WHERE project_id=?", (pid,), write=True)
    db.q("DELETE FROM project_teams WHERE project_id=?", (pid,), write=True)
    for u in dict.fromkeys(body.users):
        if db.q("SELECT 1 FROM users WHERE id=?", (u,), one=True):
            db.q("INSERT INTO project_users VALUES(?,?)", (pid, u), write=True)
    for t in dict.fromkeys(body.teams):
        if db.q("SELECT 1 FROM teams WHERE id=?", (t,), one=True):
            db.q("INSERT INTO project_teams VALUES(?,?)", (pid, t), write=True)


@router.post("/projects", status_code=201)
def create_project(body: ProjectIn, admin: dict[str, Any] = Depends(require_admin)) -> dict[str, str]:
    if db.q("SELECT 1 FROM projects WHERE name=?", (body.name,), one=True):
        raise HTTPException(409, "project name exists")
    pid = db.uid()
    db.q("INSERT INTO projects(id,name,description,token_budget,archived,created) VALUES(?,?,?,?,0,?)",
         (pid, body.name, body.description, body.token_budget, time.time()), write=True)
    _save_project(pid, body)
    db.audit(_actor(admin), "project_created", body.name)
    return {"id": pid}


@router.put("/projects/{pid}")
def update_project(pid: str, body: ProjectIn, admin: dict[str, Any] = Depends(require_admin)) -> dict[str, bool]:
    if not db.q("SELECT 1 FROM projects WHERE id=?", (pid,), one=True):
        raise HTTPException(404, "unknown project")
    db.q("UPDATE projects SET name=?, description=?, token_budget=?, archived=? WHERE id=?",
         (body.name, body.description, body.token_budget, int(body.archived), pid), write=True)
    _save_project(pid, body)
    db.audit(_actor(admin), "project_updated", body.name)
    return {"ok": True}


# --------------------------------------------------------------------------- role policies


@router.get("/policies")
def policies() -> dict[str, Any]:
    return {"roles": ROLES, "policies": db.all_policies()}


@router.put("/policies/{role}")
def put_policy(role: str, body: dict[str, Any], admin: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    if role not in ROLES:
        raise HTTPException(404, "unknown role")
    try:
        pol = validate_policy(body)
    except (ValueError, TypeError) as e:
        raise HTTPException(422, str(e)) from e
    if role == "project_admin":
        pol["agents"] = db.get_policy("project_admin")["agents"]  # the admin role cannot lock itself out
        pol["can_approve_gates"] = pol["can_edit_board"] = True
    db.q("INSERT OR REPLACE INTO role_policies(role,json) VALUES(?,?)", (role, json.dumps(pol)), write=True)
    db.audit(_actor(admin), "policy_updated", role)
    return pol


# --------------------------------------------------------------------------- AI providers (Gemini)


class ModelIn(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,60}$")
    tier: str


class ProviderIn(BaseModel):
    enabled: bool = True
    models: list[ModelIn] = Field(min_length=1)
    default_model: str
    api_key: str | None = Field(None, max_length=300)  # omit to keep the stored key; "" is rejected


@router.get("/provider")
def get_provider() -> dict[str, Any]:
    p = db.get_provider()
    key = db.provider_key()
    return {**p, "key_hint": security.mask(key) if key else None}  # the key itself is never returned


@router.put("/provider")
def put_provider(body: ProviderIn, admin: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    if any(m.tier not in MODEL_TIERS[1:] for m in body.models):
        raise HTTPException(422, "model tier must be basic or advanced")
    if body.default_model not in {m.id for m in body.models}:
        raise HTTPException(422, "default model must be one of the models")
    cfg = {"enabled": body.enabled, "models": [m.model_dump() for m in body.models], "default_model": body.default_model}
    db.q("UPDATE providers SET json=?, updated=? WHERE id='gemini'", (json.dumps(cfg), time.time()), write=True)
    if body.api_key is not None:
        if not body.api_key.strip():
            raise HTTPException(422, "api_key cannot be empty; use DELETE /provider/key to remove it")
        db.q("UPDATE providers SET key_enc=? WHERE id='gemini'", (security.encrypt(body.api_key.strip()),), write=True)
        db.audit(_actor(admin), "provider_key_set", "gemini")
    db.audit(_actor(admin), "provider_updated", f"enabled={body.enabled} models={[m.id for m in body.models]}")
    return get_provider()


@router.delete("/provider/key")
def delete_key(admin: dict[str, Any] = Depends(require_admin)) -> dict[str, bool]:
    db.q("UPDATE providers SET key_enc=NULL WHERE id='gemini'", write=True)
    db.audit(_actor(admin), "provider_key_removed", "gemini")
    return {"ok": True}


@router.post("/provider/test")
def test_provider() -> dict[str, Any]:
    """Asks Google's Models API for the model list with the stored key (the key only goes to Google)."""
    key = db.provider_key()
    if not key:
        raise HTTPException(409, "no key stored")
    try:
        r = httpx.get("https://generativelanguage.googleapis.com/v1beta/models", params={"key": key, "pageSize": 100}, timeout=12)
    except httpx.HTTPError as e:
        return {"ok": False, "message": f"could not reach Google: {type(e).__name__}"}
    if r.status_code != 200:
        msg = r.json().get("error", {}).get("message", r.text[:120]) if r.headers.get("content-type", "").startswith("application/json") else r.text[:120]
        return {"ok": False, "message": f"Google rejected the key ({r.status_code}): {msg}"}
    names = [m["name"].removeprefix("models/") for m in r.json().get("models", [])]
    configured = [m["id"] for m in db.get_provider()["models"]]
    return {"ok": True, "message": f"key works; {len(names)} models visible", "missing": [m for m in configured if m not in names]}


# --------------------------------------------------------------------------- usage and audit


@router.get("/usage")
def usage() -> dict[str, Any]:
    by_user = db.q("""SELECT u.name, u.role, COUNT(x.id) runs, COALESCE(SUM(x.prompt_tokens+x.output_tokens),0) tokens
                      FROM users u LEFT JOIN usage x ON x.user_id=u.id AND x.provider='gemini' GROUP BY u.id ORDER BY tokens DESC""")
    by_project = db.q("""SELECT p.name, p.token_budget, COUNT(x.id) runs, COALESCE(SUM(x.prompt_tokens+x.output_tokens),0) tokens
                         FROM projects p LEFT JOIN usage x ON x.project_id=p.id AND x.provider='gemini' GROUP BY p.id ORDER BY tokens DESC""")
    recent = db.q("""SELECT x.ts, u.name user, p.name project, x.provider, x.model, x.prompt_tokens, x.output_tokens
                     FROM usage x LEFT JOIN users u ON u.id=x.user_id LEFT JOIN projects p ON p.id=x.project_id ORDER BY x.ts DESC LIMIT 25""")
    return {"by_user": by_user, "by_project": by_project, "recent": recent}


@router.get("/audit")
def audit_log() -> list[dict[str, Any]]:
    return db.q("""SELECT a.ts, u.name user, a.action, a.detail FROM audit a LEFT JOIN users u ON u.id=a.user_id
                   ORDER BY a.id DESC LIMIT 100""")
