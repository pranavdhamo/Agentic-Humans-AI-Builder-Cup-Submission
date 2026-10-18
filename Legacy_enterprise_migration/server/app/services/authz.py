"""Policy enforcement for AI use: what a signed-in user may start in a project, and what is left of their budgets."""
from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any

from fastapi import HTTPException

from app import db
from app.policy import tier_allows


def day_start() -> float:
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def budgets(user: dict[str, Any], project: dict[str, Any] | None) -> dict[str, Any]:
    """Used and limit of Gemini tokens at user, team and project level, plus runs today."""
    pol = db.get_policy(user["role"])
    since = day_start()
    out: dict[str, Any] = {
        "user": {"limit": pol["daily_token_budget"], "used": db.tokens_since(since, user_id=user["id"])},
        "runs": {"limit": pol["runs_per_day"], "used": db.runs_today(user["id"], since)},
        "teams": [],
        "project": None,
    }
    for t in db.user_teams(user["id"]):
        if t["daily_token_budget"] is None:
            continue
        members = [m["user_id"] for m in db.q("SELECT user_id FROM team_members WHERE team_id=?", (t["id"],))]
        out["teams"].append({"id": t["id"], "name": t["name"], "limit": t["daily_token_budget"], "used": db.tokens_since(since, user_ids=members)})
    if project and project.get("token_budget") is not None:
        out["project"] = {"id": project["id"], "name": project["name"], "limit": project["token_budget"],
                          "used": db.tokens_since(0, project_id=project["id"])}
    return out


def gemini_key_available() -> bool:
    return bool(db.provider_key() or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))


def authorize_migration(user: dict[str, Any], project: dict[str, Any], req: dict[str, Any]) -> dict[str, Any]:
    """Raises 403 with every reason found; returns the normalised request that may run."""
    pol = db.get_policy(user["role"])
    agents = set(pol["agents"])
    problems: list[str] = []

    if req["provider"] not in pol["providers"]:
        problems.append(f"your role may not use the {req['provider']} provider")
    if "generator" not in agents:
        problems.append("your role cannot run the code generator agent")
    if req["mode"] not in pol["modes"]:
        problems.append(f"prompt mode '{req['mode']}' is not allowed for your role")
    limit = pol["max_repairs"] if "repair" in agents else 0
    if req["max_repairs"] > limit:
        problems.append(f"your role allows at most {limit} repair(s)")
    if req.get("gates") and "gate" not in agents:
        problems.append("your role cannot place human review gates")

    model = req.get("model")
    if req["provider"] == "gemini":
        prov = db.get_provider()
        if not prov["enabled"]:
            problems.append("the Gemini provider is disabled by the admin")
        elif not gemini_key_available():
            problems.append("no Gemini API key is configured (an admin must add one)")
        models = {m["id"]: m for m in prov["models"]}
        model = model or prov["default_model"]
        if model not in models:
            problems.append(f"model '{model}' is not enabled for this workspace")
        elif not tier_allows(pol["model_tier"], models[model]["tier"]):
            problems.append(f"model '{model}' ({models[model]['tier']} tier) is above your role's tier ({pol['model_tier']})")
        b = budgets(user, project)
        if b["user"]["used"] >= b["user"]["limit"]:
            problems.append("your daily token budget is used up")
        for t in b["teams"]:
            if t["used"] >= t["limit"]:
                problems.append(f"team '{t['name']}' has used its daily token budget")
        if b["project"] and b["project"]["used"] >= b["project"]["limit"]:
            problems.append(f"project '{project['name']}' has used its token budget")
    else:
        model = None

    if db.runs_today(user["id"], day_start()) >= pol["runs_per_day"]:
        problems.append("your daily run limit is reached")

    if problems:
        raise HTTPException(403, "; ".join(problems))
    return {**req, "model": model, "gates": [g for g in req.get("gates", []) if g in ("generate", "repair")]}


def record_usage(job) -> None:
    """Called when a migration finishes: log tokens and remember which project and user own the run."""
    if job.kind != "migrate" or not job.result.get("run"):
        return
    run_name = job.result["run"].split(":", 1)[1]
    o = job.owner
    db.q("INSERT OR REPLACE INTO runs_meta(run_name,project_id,user_id,job_id) VALUES(?,?,?,?)",
         (run_name, o.get("project_id"), o.get("user_id"), job.id), write=True)
    pt = sum(a["prompt_tokens"] for a in job.result.get("attempts", []))
    ot = sum(a["output_tokens"] for a in job.result.get("attempts", []))
    db.q("INSERT INTO usage(ts,user_id,project_id,job_id,provider,model,prompt_tokens,output_tokens) VALUES(?,?,?,?,?,?,?,?)",
         (time.time(), o.get("user_id"), o.get("project_id"), job.id, job.params["provider"], job.params.get("model"), pt, ot), write=True)
