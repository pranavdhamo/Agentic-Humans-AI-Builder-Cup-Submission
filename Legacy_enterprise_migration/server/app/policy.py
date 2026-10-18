"""Role policies: what each seniority level may do with the AI agents, and how much it may spend.

A policy is plain data (editable by the project admin). Effective limits are the intersection of the role policy,
the user's teams (daily token budget across the team) and the project (total token budget).
"""
from __future__ import annotations

from typing import Any

ROLES = ["project_admin", "lead_architect", "senior_dev", "junior_dev", "intern"]
ROLE_LABELS = {
    "project_admin": "Project Admin", "lead_architect": "Lead Architect", "senior_dev": "Senior Developer",
    "junior_dev": "Junior Developer", "intern": "Intern",
}

# Agents are the node types of the orchestration board; a role may only place and run the agents it holds.
AGENTS = {
    "source": "COBOL Source", "generator": "Gemini Code Generator", "build": "Build (Maven)", "verify": "Verifier (vs COBOL oracle)",
    "repair": "Repair Loop", "gate": "Human Review Gate", "done": "Result",
}
MODEL_TIERS = ["none", "basic", "advanced"]

DEFAULT_POLICIES: dict[str, dict[str, Any]] = {
    "project_admin": dict(
        providers=["mock", "gemini"], model_tier="advanced", max_repairs=8, modes=["guided", "naive"],
        agents=list(AGENTS), can_approve_gates=True, can_edit_board=True, can_run_verifier=True, can_run_mutation=True,
        can_run_build=True, runs_per_day=100, daily_token_budget=1_000_000,
    ),
    "lead_architect": dict(
        providers=["mock", "gemini"], model_tier="advanced", max_repairs=8, modes=["guided", "naive"],
        agents=list(AGENTS), can_approve_gates=True, can_edit_board=True, can_run_verifier=True, can_run_mutation=True,
        can_run_build=True, runs_per_day=40, daily_token_budget=400_000,
    ),
    "senior_dev": dict(
        providers=["mock", "gemini"], model_tier="basic", max_repairs=5, modes=["guided", "naive"],
        agents=["source", "generator", "build", "verify", "repair", "gate", "done"], can_approve_gates=True, can_edit_board=True,
        can_run_verifier=True, can_run_mutation=True, can_run_build=True, runs_per_day=20, daily_token_budget=200_000,
    ),
    "junior_dev": dict(
        providers=["mock", "gemini"], model_tier="basic", max_repairs=2, modes=["guided"],
        agents=["source", "generator", "build", "verify", "repair", "done"], can_approve_gates=False, can_edit_board=False,
        can_run_verifier=True, can_run_mutation=False, can_run_build=True, runs_per_day=6, daily_token_budget=80_000,
    ),
    "intern": dict(
        providers=["mock"], model_tier="none", max_repairs=0, modes=["guided"],
        agents=["source", "generator", "build", "verify", "done"], can_approve_gates=False, can_edit_board=False,
        can_run_verifier=True, can_run_mutation=False, can_run_build=False, runs_per_day=3, daily_token_budget=0,
    ),
}

DEFAULT_PROVIDER: dict[str, Any] = {
    "enabled": True,
    "models": [{"id": "gemini-3.8-flash", "tier": "basic"}],
    "default_model": "gemini-3.8-flash",
}

POLICY_BOOLS = ["can_approve_gates", "can_edit_board", "can_run_verifier", "can_run_mutation", "can_run_build"]
POLICY_INTS = ["max_repairs", "runs_per_day", "daily_token_budget"]


def validate_policy(p: dict[str, Any]) -> dict[str, Any]:
    """Normalise an admin-supplied policy; raises ValueError with a readable message."""
    out: dict[str, Any] = {}
    out["providers"] = [x for x in p.get("providers", []) if x in ("mock", "gemini")]
    if "mock" not in out["providers"]:
        out["providers"].insert(0, "mock")
    if p.get("model_tier") not in MODEL_TIERS:
        raise ValueError("model_tier must be none, basic or advanced")
    out["model_tier"] = p["model_tier"]
    out["modes"] = [m for m in p.get("modes", []) if m in ("guided", "naive")] or ["guided"]
    out["agents"] = [a for a in p.get("agents", []) if a in AGENTS]
    for k in POLICY_BOOLS:
        out[k] = bool(p.get(k, False))
    for k in POLICY_INTS:
        v = int(p.get(k, 0))
        if v < 0 or v > 10_000_000:
            raise ValueError(f"{k} out of range")
        out[k] = v
    if out["max_repairs"] > 8:
        raise ValueError("max_repairs cannot exceed 8")
    return out


def tier_allows(role_tier: str, model_tier: str) -> bool:
    return MODEL_TIERS.index(role_tier) >= MODEL_TIERS.index(model_tier) and role_tier != "none"
