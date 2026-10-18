import time

import pytest
from conftest import auth

from app.config import settings


def wait(client, headers, job_id, timeout=150):
    for _ in range(timeout * 2):
        j = client.get(f"/api/jobs/{job_id}", headers=headers).json()
        if j["status"] not in ("queued", "running"):
            return j
        time.sleep(0.5)
    raise AssertionError("job did not finish")


# ------------------------------------------------------------------ auth


def test_health_is_public(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_routes_require_sign_in(client):
    for path in ("/api/scenarios", "/api/runs", "/api/jobs", "/api/environment", "/api/admin/users", "/api/auth/me"):
        assert client.get(path).status_code == 401, path


def test_login_rejects_bad_password(client):
    assert client.post("/api/auth/login", json={"email": "admin@studio.local", "password": "wrong"}).status_code == 401


def test_forged_and_expired_tokens_rejected(client):
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer abc.def"}).status_code == 401
    from app import security
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {security.make_token('x', ttl=-5)}"}).status_code == 401


def test_profile_carries_role_policy_and_projects(tokens):
    intern, lead = tokens["intern"], tokens["architect"]
    assert intern["policy"]["providers"] == ["mock"] and intern["policy"]["model_tier"] == "none"
    assert lead["policy"]["model_tier"] == "advanced"
    assert len(intern["projects"]) == 1


# ------------------------------------------------------------------ catalog (needs sign-in only)


def test_scenarios_and_golden(client, tokens):
    h = auth(tokens, "intern")
    assert len(client.get("/api/scenarios", headers=h).json()) == 8
    r = client.get("/api/golden", params={"scenario": "posttran/edge", "artifact": "TRANSACT.flat", "limit": 5}, headers=h)
    assert r.status_code == 200 and len(r.json()["rows"]) == 5


def test_run_path_traversal_rejected(client, tokens):
    assert client.get("/api/runs/results/..%2F..%2Fsecret", headers=auth(tokens, "admin")).status_code == 404


def test_curated_results_visible_to_all(client, tokens):
    runs = client.get("/api/runs", headers=auth(tokens, "intern")).json()
    assert any(r["source"] == "results" for r in runs)


# ------------------------------------------------------------------ RBAC and policy enforcement


def body(project_id, **kw):
    return {"project_id": project_id, "program": "intcalc", "provider": "mock", "mode": "guided", "max_repairs": 0, **kw}


def test_admin_console_is_admin_only(client, tokens):
    for who in ("architect", "senior", "junior", "intern"):
        assert client.get("/api/admin/users", headers=auth(tokens, who)).status_code == 403
    assert client.get("/api/admin/users", headers=auth(tokens, "admin")).status_code == 200


def test_intern_cannot_use_gemini_or_repairs(client, tokens, project_id):
    r = client.post("/api/jobs/migrate", json=body(project_id, provider="gemini"), headers=auth(tokens, "intern"))
    assert r.status_code == 403 and "gemini" in r.text
    r = client.post("/api/jobs/migrate", json=body(project_id, max_repairs=2), headers=auth(tokens, "intern"))
    assert r.status_code == 403 and "at most 0 repair" in r.text


def test_junior_limits(client, tokens, project_id):
    h = auth(tokens, "junior")
    assert client.post("/api/jobs/migrate", json=body(project_id, max_repairs=3), headers=h).status_code == 403
    r = client.post("/api/jobs/migrate", json=body(project_id, gates=["repair"]), headers=h)
    assert r.status_code == 403 and "gates" in r.text
    assert client.post("/api/jobs/mutation", headers=h).status_code == 403


def test_gemini_needs_admin_configured_key(client, tokens, project_id, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    r = client.post("/api/jobs/migrate", json=body(project_id, provider="gemini"), headers=auth(tokens, "senior"))
    assert r.status_code == 403 and "no Gemini API key" in r.text


def test_project_scoping(client, tokens):
    admin = auth(tokens, "admin")
    pid = client.post("/api/admin/projects", json={"name": "Secret", "users": [tokens["admin"]["user"]["id"]]}, headers=admin).json()["id"]
    r = client.post("/api/jobs/migrate", json=body(pid), headers=auth(tokens, "senior"))
    assert r.status_code == 403 and "not assigned" in r.text
    assert client.get(f"/api/projects/{pid}/board", headers=auth(tokens, "senior")).status_code == 403


# ------------------------------------------------------------------ admin: users, teams, provider key


def test_admin_onboards_user_who_can_sign_in(client, tokens):
    admin = auth(tokens, "admin")
    r = client.post("/api/admin/users", json={"email": "new@studio.local", "name": "New Dev", "role": "junior_dev", "password": "longenough1"}, headers=admin)
    assert r.status_code == 201
    assert client.post("/api/auth/login", json={"email": "new@studio.local", "password": "longenough1"}).status_code == 200
    assert client.post("/api/admin/users", json={"email": "new@studio.local", "name": "x", "role": "intern", "password": "longenough1"}, headers=admin).status_code == 409


def test_admin_cannot_lock_self_out(client, tokens):
    me = tokens["admin"]["user"]["id"]
    r = client.patch(f"/api/admin/users/{me}", json={"active": False}, headers=auth(tokens, "admin"))
    assert r.status_code == 409


def test_provider_key_is_encrypted_and_never_returned(client, tokens):
    admin = auth(tokens, "admin")
    secret = "AIzaSyTESTKEY1234567890abcdefghijk"
    cfg = {"enabled": True, "models": [{"id": "gemini-3.8-flash", "tier": "basic"}, {"id": "gemini-pro-x", "tier": "advanced"}],
           "default_model": "gemini-3.8-flash", "api_key": secret}
    r = client.put("/api/admin/provider", json=cfg, headers=admin)
    assert r.status_code == 200 and r.json()["has_key"] is True
    assert secret not in r.text and secret not in client.get("/api/admin/provider", headers=admin).text
    from app import db
    stored = db.q("SELECT key_enc FROM providers WHERE id='gemini'", one=True)["key_enc"]
    assert secret not in stored and db.provider_key() == secret
    # a basic-tier role may not pick an advanced model; an architect may
    pid = tokens["admin"]["projects"][0]["id"]
    r = client.post("/api/jobs/migrate", json=body(pid, provider="gemini", model="gemini-pro-x"), headers=auth(tokens, "senior"))
    assert r.status_code == 403 and "above your role" in r.text
    client.delete("/api/admin/provider/key", headers=admin)
    assert client.get("/api/admin/provider", headers=admin).json()["has_key"] is False


def test_role_policy_edit_takes_effect(client, tokens, project_id):
    admin = auth(tokens, "admin")
    pol = client.get("/api/admin/policies", headers=admin).json()["policies"]["junior_dev"]
    assert client.put("/api/admin/policies/junior_dev", json={**pol, "max_repairs": 9}, headers=admin).status_code == 422
    client.put("/api/admin/policies/junior_dev", json={**pol, "runs_per_day": 0}, headers=admin)
    r = client.post("/api/jobs/migrate", json=body(project_id), headers=auth(tokens, "junior"))
    assert r.status_code == 403 and "daily run limit" in r.text
    client.put("/api/admin/policies/junior_dev", json=pol, headers=admin)


# ------------------------------------------------------------------ orchestration board


def test_default_board_compiles_and_bad_board_is_rejected(client, tokens, project_id):
    h = auth(tokens, "senior")
    b = client.get(f"/api/projects/{project_id}/board", headers=h).json()
    assert b["compiled"]["ok"] and b["compiled"]["params"]["program"] == "posttran"
    broken = {"nodes": [n for n in b["graph"]["nodes"] if n["type"] != "build"], "edges": b["graph"]["edges"]}
    r = client.post(f"/api/projects/{project_id}/board/validate", json=broken, headers=h).json()
    assert not r["ok"] and any("Build" in e for e in r["errors"])


def test_board_editing_and_agents_follow_role(client, tokens, project_id):
    graph = client.get(f"/api/projects/{project_id}/board", headers=auth(tokens, "senior")).json()["graph"]
    assert client.put(f"/api/projects/{project_id}/board", json=graph, headers=auth(tokens, "junior")).status_code == 403
    assert client.put(f"/api/projects/{project_id}/board", json=graph, headers=auth(tokens, "senior")).status_code == 200
    # an intern validating a board with a repair node is told the role lacks that agent
    r = client.post(f"/api/projects/{project_id}/board/validate", json=graph, headers=auth(tokens, "intern")).json()
    assert not r["ok"] and any("repair" in e for e in r["errors"])


# ------------------------------------------------------------------ live pipeline (needs Java + CardDemo source)

needs_pipeline = pytest.mark.skipif(not (__import__("shutil").which("java") and settings.carddemo_src.exists() and settings.jar.exists()),
                                    reason="needs JDK, built jar and CardDemo source")


@needs_pipeline
def test_verify_job_streams_events(client, tokens, project_id):
    h = auth(tokens, "senior")
    job = client.post("/api/jobs/verify", json={"only": "intcalc/sample", "project_id": project_id}, headers=h).json()
    assert wait(client, h, job["id"])["status"] == "passed"
    stream = client.get(f"/api/jobs/{job['id']}/events", headers=h).text
    assert '"type": "scenario"' in stream and "event: end" in stream


@needs_pipeline
def test_human_gate_pauses_run_and_hint_reaches_the_model(client, tokens, project_id):
    senior, junior = auth(tokens, "senior"), auth(tokens, "junior")
    job = client.post("/api/jobs/migrate", json=body(project_id, max_repairs=2, gates=["repair"]), headers=senior)
    assert job.status_code == 202, job.text
    jid = job.json()["id"]
    gate = None
    for _ in range(240):  # wait for the pause
        gate = client.get(f"/api/jobs/{jid}", headers=senior).json()["pending_gate"]
        if gate:
            break
        time.sleep(0.5)
    assert gate and gate["point"] == "repair"
    # a junior (no approval right) cannot answer, the senior can
    r = client.post(f"/api/jobs/{jid}/gate", json={"gate_id": gate["id"], "action": "approve", "hint": "x"}, headers=junior)
    assert r.status_code == 403
    r = client.post(f"/api/jobs/{jid}/gate", json={"gate_id": gate["id"], "action": "approve", "hint": "Check the last-account interest rule"}, headers=senior)
    assert r.status_code == 200
    # second gate: stop the run
    for _ in range(240):
        g2 = client.get(f"/api/jobs/{jid}", headers=senior).json()["pending_gate"]
        if g2 and g2["id"] != gate["id"]:
            client.post(f"/api/jobs/{jid}/gate", json={"gate_id": g2["id"], "action": "stop"}, headers=senior)
            break
        time.sleep(0.5)
    done = wait(client, senior, jid)
    assert done["result"]["stopped_by_reviewer"] is True and done["status"] == "failed"
    events = client.get(f"/api/jobs/{jid}/events", headers=senior).text
    assert '"type": "gate"' in events and '"type": "gate_done"' in events


@needs_pipeline
def test_migration_is_recorded_against_project_and_visible_to_members_only(client, tokens, project_id):
    senior = auth(tokens, "senior")
    jid = client.post("/api/jobs/migrate", json=body(project_id, program="intcalc", max_repairs=3), headers=senior).json()["id"]
    done = wait(client, senior, jid)
    assert done["status"] == "passed", done
    name = done["result"]["run"].split(":", 1)[1]
    mine = client.get("/api/runs", params={"project_id": project_id}, headers=senior).json()
    assert any(r["name"] == name and r["started_by"] == "Aisha Senior" for r in mine)
    other = client.post("/api/admin/users", json={"email": "out@studio.local", "name": "Out", "role": "senior_dev", "password": "longenough1"}, headers=auth(tokens, "admin"))
    assert other.status_code == 201
    from conftest import login
    outsider = {"Authorization": f"Bearer {login(client, 'out@studio.local', 'longenough1')['token']}"}
    assert client.get(f"/api/runs/runs/{name}", headers=outsider).status_code == 404
