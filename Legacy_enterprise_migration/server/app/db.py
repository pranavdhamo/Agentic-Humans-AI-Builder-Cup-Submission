"""SQLite persistence for users, teams, projects, policies, providers, boards, usage and the audit log."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from typing import Any

from app import security
from app.policy import DEFAULT_POLICIES, DEFAULT_PROVIDER, ROLES

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL, role TEXT NOT NULL,
  pw_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS teams(id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL, daily_token_budget INTEGER);
CREATE TABLE IF NOT EXISTS team_members(team_id TEXT NOT NULL, user_id TEXT NOT NULL, PRIMARY KEY(team_id, user_id));
CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL, description TEXT NOT NULL DEFAULT '',
  token_budget INTEGER, archived INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS project_users(project_id TEXT NOT NULL, user_id TEXT NOT NULL, PRIMARY KEY(project_id, user_id));
CREATE TABLE IF NOT EXISTS project_teams(project_id TEXT NOT NULL, team_id TEXT NOT NULL, PRIMARY KEY(project_id, team_id));
CREATE TABLE IF NOT EXISTS role_policies(role TEXT PRIMARY KEY, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS providers(id TEXT PRIMARY KEY, json TEXT NOT NULL, key_enc TEXT, updated REAL);
CREATE TABLE IF NOT EXISTS boards(project_id TEXT PRIMARY KEY, json TEXT NOT NULL, updated_by TEXT, updated REAL);
CREATE TABLE IF NOT EXISTS usage(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, user_id TEXT, project_id TEXT, job_id TEXT,
  provider TEXT, model TEXT, prompt_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS runs_meta(run_name TEXT PRIMARY KEY, project_id TEXT, user_id TEXT, job_id TEXT);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, user_id TEXT, action TEXT NOT NULL, detail TEXT);
"""


def uid() -> str:
    return uuid.uuid4().hex[:10]


def connect(path: str | None = None) -> sqlite3.Connection:
    """(Re)open the database. `path=':memory:'` is used by tests."""
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
        if path is None:
            security.DATA_DIR.mkdir(parents=True, exist_ok=True)
            path = str(security.DATA_DIR / "studio.db")
        _conn = sqlite3.connect(path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
        _conn.commit()
        return _conn


def q(sql: str, args: tuple | list = (), *, one: bool = False, write: bool = False) -> Any:
    with _lock:
        if _conn is None:
            connect()
        assert _conn is not None
        cur = _conn.execute(sql, args)
        if write:
            _conn.commit()
            return cur.lastrowid
        rows = [dict(r) for r in cur.fetchall()]
        return (rows[0] if rows else None) if one else rows


def audit(user_id: str | None, action: str, detail: str = "") -> None:
    q("INSERT INTO audit(ts,user_id,action,detail) VALUES(?,?,?,?)", (time.time(), user_id, action, detail), write=True)


# --------------------------------------------------------------------------- seed


def seed(admin_password: str = "admin123", demo_password: str = "studio123") -> None:
    """Idempotent first-run data: role policies, Gemini provider shell, demo users, one team and one project."""
    for role, pol in DEFAULT_POLICIES.items():
        if not q("SELECT 1 FROM role_policies WHERE role=?", (role,), one=True):
            q("INSERT INTO role_policies(role,json) VALUES(?,?)", (role, json.dumps(pol)), write=True)
    if not q("SELECT 1 FROM providers WHERE id='gemini'", one=True):
        q("INSERT INTO providers(id,json,key_enc,updated) VALUES('gemini',?,NULL,?)", (json.dumps(DEFAULT_PROVIDER), time.time()), write=True)
    if q("SELECT COUNT(*) n FROM users", one=True)["n"]:
        return
    demo = [
        ("admin@studio.local", "Priya Admin", "project_admin", admin_password),
        ("architect@studio.local", "Marcus Lead", "lead_architect", demo_password),
        ("senior@studio.local", "Aisha Senior", "senior_dev", demo_password),
        ("junior@studio.local", "Tom Junior", "junior_dev", demo_password),
        ("intern@studio.local", "Jin Intern", "intern", demo_password),
    ]
    ids = {}
    for email, name, role, pw in demo:
        ids[role] = uid()
        q("INSERT INTO users(id,email,name,role,pw_hash,active,created) VALUES(?,?,?,?,?,1,?)",
          (ids[role], email, name, role, security.hash_password(pw), time.time()), write=True)
    team = uid()
    q("INSERT INTO teams(id,name,daily_token_budget) VALUES(?,?,?)", (team, "Mainframe Modernization", 400_000), write=True)
    for role in ("lead_architect", "senior_dev", "junior_dev", "intern"):
        q("INSERT INTO team_members VALUES(?,?)", (team, ids[role]), write=True)
    pid = uid()
    q("INSERT INTO projects(id,name,description,token_budget,archived,created) VALUES(?,?,?,?,0,?)",
      (pid, "CardDemo Core Batch", "CBTRN02C posting and CBACT04C interest: COBOL to Spring Batch", 2_000_000, time.time()), write=True)
    q("INSERT INTO project_teams VALUES(?,?)", (pid, team), write=True)
    q("INSERT INTO project_users VALUES(?,?)", (pid, ids["project_admin"]), write=True)


# --------------------------------------------------------------------------- queries


def get_policy(role: str) -> dict[str, Any]:
    row = q("SELECT json FROM role_policies WHERE role=?", (role,), one=True)
    base = DEFAULT_POLICIES.get(role, DEFAULT_POLICIES["intern"])
    return {**base, **(json.loads(row["json"]) if row else {})}


def all_policies() -> dict[str, dict[str, Any]]:
    return {r: get_policy(r) for r in ROLES}


def get_provider() -> dict[str, Any]:
    row = q("SELECT json,key_enc,updated FROM providers WHERE id='gemini'", one=True)
    cfg = {**DEFAULT_PROVIDER, **(json.loads(row["json"]) if row else {})}
    return {**cfg, "has_key": bool(row and row["key_enc"]), "updated": row["updated"] if row else None}


def provider_key() -> str | None:
    row = q("SELECT key_enc FROM providers WHERE id='gemini'", one=True)
    return security.decrypt(row["key_enc"]) if row and row["key_enc"] else None


def user_projects(user: dict[str, Any]) -> list[dict[str, Any]]:
    """Projects the user can open: directly assigned, via a team, or all of them for the project admin."""
    if user["role"] == "project_admin":
        return q("SELECT * FROM projects WHERE archived=0 ORDER BY name")
    return q(
        """SELECT DISTINCT p.* FROM projects p
           LEFT JOIN project_users pu ON pu.project_id=p.id AND pu.user_id=?
           LEFT JOIN project_teams pt ON pt.project_id=p.id
           LEFT JOIN team_members tm ON tm.team_id=pt.team_id AND tm.user_id=?
           WHERE p.archived=0 AND (pu.user_id IS NOT NULL OR tm.user_id IS NOT NULL) ORDER BY p.name""",
        (user["id"], user["id"]),
    )


def user_teams(user_id: str) -> list[dict[str, Any]]:
    return q("SELECT t.* FROM teams t JOIN team_members m ON m.team_id=t.id WHERE m.user_id=?", (user_id,))


def tokens_since(since: float, *, user_id: str | None = None, project_id: str | None = None, user_ids: list[str] | None = None) -> int:
    sql, args = "SELECT COALESCE(SUM(prompt_tokens+output_tokens),0) n FROM usage WHERE ts>=? AND provider='gemini'", [since]
    if user_id:
        sql += " AND user_id=?"; args.append(user_id)
    if project_id:
        sql += " AND project_id=?"; args.append(project_id)
    if user_ids is not None:
        if not user_ids:
            return 0
        sql += f" AND user_id IN ({','.join('?' * len(user_ids))})"; args += user_ids
    return int(q(sql, args, one=True)["n"])


def runs_today(user_id: str, since: float) -> int:
    return int(q("SELECT COUNT(*) n FROM usage WHERE user_id=? AND ts>=?", (user_id, since), one=True)["n"])
