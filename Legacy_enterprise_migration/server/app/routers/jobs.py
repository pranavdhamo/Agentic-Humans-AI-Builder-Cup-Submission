"""Job control, human review gates and live event streaming (Server-Sent Events). Everything needs a signed-in user."""
from __future__ import annotations

import asyncio
import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app import db
from app.deps import current_user, need, project_for
from app.jobs import BusyError, Job, manager
from app.services import authz

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class MigrateParams(BaseModel):
    project_id: str
    program: Literal["posttran", "intcalc"]
    provider: Literal["mock", "gemini"] = "mock"
    mode: Literal["guided", "naive"] = "guided"
    max_repairs: int = Field(4, ge=0, le=8)
    model: str | None = Field(None, max_length=60, pattern=r"^[A-Za-z0-9._-]*$")
    gates: list[Literal["generate", "repair"]] = []
    gate_timeout: int = Field(1200, ge=30, le=7200)


class VerifyParams(BaseModel):
    only: str = Field("", max_length=60, pattern=r"^[A-Za-z0-9/_-]*$")
    project_id: str | None = None


class GateAnswer(BaseModel):
    gate_id: str
    action: Literal["approve", "stop"]
    hint: str = Field("", max_length=4000)


def _owner(user: dict[str, Any], project_id: str | None) -> dict[str, Any]:
    return {"project_id": project_id, "user_id": user["id"], "user_name": user["name"]}


def _start(kind: str, params: dict, user: dict[str, Any], project_id: str | None = None, env: dict[str, str] | None = None) -> dict:
    try:
        return manager.start(kind, params, owner=_owner(user, project_id), env=env).public()
    except BusyError as e:
        raise HTTPException(409, str(e)) from e


def _visible(job: Job, user: dict[str, Any]) -> bool:
    pid = job.owner.get("project_id")
    if user["role"] == "project_admin" or job.owner.get("user_id") == user["id"]:
        return True
    return pid is not None and any(p["id"] == pid for p in db.user_projects(user))


def _job_for(job_id: str, user: dict[str, Any]) -> Job:
    job = manager.get(job_id)
    if job is None or not _visible(job, user):
        raise HTTPException(404, "unknown job")
    return job


@router.post("/migrate", status_code=202)
def start_migrate(p: MigrateParams, user: dict[str, Any] = Depends(current_user)) -> dict:
    project = project_for(user, p.project_id)
    req = authz.authorize_migration(user, project, p.model_dump(exclude={"project_id"}))
    env = {}
    if req["provider"] == "gemini" and db.provider_key():
        env["GEMINI_API_KEY"] = db.provider_key() or ""
    db.audit(user["id"], "migration_started", f"{req['program']} {req['provider']} project={p.project_id}")
    return _start("migrate", req, user, p.project_id, env)


@router.post("/verify", status_code=202)
def start_verify(p: VerifyParams, user: dict[str, Any] = Depends(current_user)) -> dict:
    need(user, "can_run_verifier")
    if p.project_id:
        project_for(user, p.project_id)
    return _start("verify", {"only": p.only}, user, p.project_id)


@router.post("/build", status_code=202)
def start_build(user: dict[str, Any] = Depends(current_user)) -> dict:
    need(user, "can_run_build")
    return _start("build", {}, user)


@router.post("/mutation", status_code=202)
def start_mutation(user: dict[str, Any] = Depends(current_user)) -> dict:
    need(user, "can_run_mutation")
    return _start("mutation", {}, user)


@router.get("")
def list_jobs(project_id: str | None = None, user: dict[str, Any] = Depends(current_user)) -> list[dict]:
    jobs = [j for j in manager.list() if _visible(j, user)]
    if project_id:
        jobs = [j for j in jobs if j.owner.get("project_id") == project_id]
    return [j.public() for j in jobs]


@router.get("/{job_id}")
def get_job(job_id: str, user: dict[str, Any] = Depends(current_user)) -> dict:
    return _job_for(job_id, user).public()


@router.post("/{job_id}/cancel")
def cancel(job_id: str, user: dict[str, Any] = Depends(current_user)) -> dict:
    job = _job_for(job_id, user)
    if job.owner.get("user_id") != user["id"] and not db.get_policy(user["role"])["can_approve_gates"]:
        raise HTTPException(403, "only the starter or a reviewer can cancel this job")
    manager.cancel(job)
    return job.public()


@router.post("/{job_id}/gate")
def answer_gate(job_id: str, body: GateAnswer, user: dict[str, Any] = Depends(current_user)) -> dict:
    """A reviewer answers a paused run: approve (optionally with a hint for the model) or stop it."""
    job = _job_for(job_id, user)
    need(user, "can_approve_gates")
    try:
        job.answer_gate(body.gate_id, body.action, body.hint, user["name"])
    except KeyError as e:
        raise HTTPException(409, "that gate is no longer pending") from e
    db.audit(user["id"], "gate_answered", f"job {job.id} {body.gate_id} {body.action}")
    return {"ok": True}


@router.get("/{job_id}/events")
async def events(job_id: str, after: int = -1, user: dict[str, Any] = Depends(current_user)) -> StreamingResponse:
    """SSE stream: replays every event after `after`, then follows the job until it finishes. Auth via ?token=."""
    job = _job_for(job_id, user)

    async def gen():
        cursor = after + 1
        while True:
            while cursor < len(job.events):
                yield f"id: {cursor}\ndata: {json.dumps(job.events[cursor])}\n\n"
                cursor += 1
            if job.finished is not None and cursor >= len(job.events):
                yield "event: end\ndata: {}\n\n"
                return
            await asyncio.sleep(0.25)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
