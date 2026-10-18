"""Sign-in and the signed-in user's profile (role, effective policy, projects, budgets)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import db, security
from app.deps import current_user
from app.policy import AGENTS, ROLE_LABELS
from app.services import authz

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Login(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)


class PasswordChange(BaseModel):
    current: str = Field(max_length=200)
    new: str = Field(min_length=8, max_length=200)


def profile(user: dict[str, Any]) -> dict[str, Any]:
    pol = db.get_policy(user["role"])
    prov = db.get_provider()
    return {
        "user": {**user, "role_label": ROLE_LABELS.get(user["role"], user["role"])},
        "policy": pol,
        "agents": [{"id": a, "label": AGENTS[a], "allowed": a in pol["agents"]} for a in AGENTS],
        "projects": db.user_projects(user),
        "provider": {"enabled": prov["enabled"], "has_key": prov["has_key"] or authz.gemini_key_available(), "models": prov["models"],
                     "default_model": prov["default_model"]},
        "budgets": authz.budgets(user, None),
    }


@router.post("/login")
def login(body: Login) -> dict[str, Any]:
    user = db.q("SELECT * FROM users WHERE lower(email)=lower(?)", (body.email.strip(),), one=True)
    if not user or not user["active"] or not security.verify_password(body.password, user["pw_hash"]):
        db.audit(user["id"] if user else None, "login_failed", body.email[:80])
        raise HTTPException(401, "invalid email or password")
    db.audit(user["id"], "login")
    pub = {k: user[k] for k in ("id", "email", "name", "role", "active")}
    return {"token": security.make_token(user["id"]), **profile(pub)}


@router.get("/me")
def me(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return profile(user)


@router.post("/password")
def change_password(body: PasswordChange, user: dict[str, Any] = Depends(current_user)) -> dict[str, bool]:
    row = db.q("SELECT pw_hash FROM users WHERE id=?", (user["id"],), one=True)
    if not row or not security.verify_password(body.current, row["pw_hash"]):
        raise HTTPException(403, "current password is wrong")
    db.q("UPDATE users SET pw_hash=? WHERE id=?", (security.hash_password(body.new), user["id"]), write=True)
    db.audit(user["id"], "password_changed")
    return {"ok": True}
