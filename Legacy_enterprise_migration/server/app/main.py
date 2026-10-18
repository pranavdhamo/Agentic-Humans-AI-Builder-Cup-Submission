"""FastAPI entry point.

    cd server && uvicorn app.main:app --reload --port 8000     # docs at /docs
"""
from __future__ import annotations

import logging
import os
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__, db
from app.config import settings
from app.jobs import manager
from app.routers import admin, api, auth, jobs, projects
from app.services import authz

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
log = logging.getLogger("studio")

app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description="AI studio for the COBOL to Java migration: oracle golden data, Gemini pipeline, differential verifier.",
)
app.add_middleware(
    CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)


@app.middleware("http")
async def timing(request: Request, call_next):
    t0 = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Process-Time-Ms"] = f"{(time.perf_counter() - t0) * 1000:.1f}"
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "internal server error", "error": type(exc).__name__})


@app.on_event("startup")
def startup() -> None:
    db.connect()
    db.seed(os.environ.get("STUDIO_ADMIN_PASSWORD", "admin123"), os.environ.get("STUDIO_DEMO_PASSWORD", "studio123"))


manager.on_finish = authz.record_usage

for r in (api.public, api.router, auth.router, admin.router, projects.router, jobs.router):
    app.include_router(r)


@app.get("/")
def root() -> dict:
    return {"service": settings.app_name, "version": __version__, "docs": "/docs", "health": "/api/health"}
