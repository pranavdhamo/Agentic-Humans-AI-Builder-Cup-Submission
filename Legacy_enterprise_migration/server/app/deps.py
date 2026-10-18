"""FastAPI dependencies: the signed-in user, admin guard and project access."""
from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Query, Request

from app import db, security


def current_user(request: Request, token: str | None = Query(None)) -> dict[str, Any]:
    """Bearer header, or `?token=` for EventSource (which cannot set headers)."""
    auth = request.headers.get("authorization", "")
    raw = auth[7:] if auth.lower().startswith("bearer ") else token
    uid = security.read_token(raw) if raw else None
    user = db.q("SELECT id,email,name,role,active FROM users WHERE id=?", (uid,), one=True) if uid else None
    if not user or not user["active"]:
        raise HTTPException(401, "not signed in")
    return user


def require_admin(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    if user["role"] != "project_admin":
        raise HTTPException(403, "project admin only")
    return user


def project_for(user: dict[str, Any], project_id: str) -> dict[str, Any]:
    proj = next((p for p in db.user_projects(user) if p["id"] == project_id), None)
    if proj is None:
        raise HTTPException(403, "you are not assigned to this project")
    return proj


def need(user: dict[str, Any], flag: str) -> dict[str, Any]:
    pol = db.get_policy(user["role"])
    if not pol.get(flag):
        raise HTTPException(403, f"your role ({user['role']}) is not allowed to do this")
    return pol
