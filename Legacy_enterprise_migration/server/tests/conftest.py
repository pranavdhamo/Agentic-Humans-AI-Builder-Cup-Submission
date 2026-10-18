import os
import tempfile

# An isolated data dir and in-memory database for every test session, set before the app is imported.
os.environ["STUDIO_DATA_DIR"] = tempfile.mkdtemp(prefix="studio-test-")
os.environ["STUDIO_SECRET"] = "test-secret"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    db.connect(":memory:")
    db.seed("admin-pass-1", "demo-pass-1")
    return TestClient(app)


def login(client, email: str, password: str = "demo-pass-1") -> dict:
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="session")
def tokens(client):
    out = {"admin": login(client, "admin@studio.local", "admin-pass-1")}
    for k in ("architect", "senior", "junior", "intern"):
        out[k] = login(client, f"{k}@studio.local")
    return out


def auth(tokens, who: str) -> dict:
    return {"Authorization": f"Bearer {tokens[who]['token']}"}


@pytest.fixture(scope="session")
def project_id(tokens):
    return tokens["admin"]["projects"][0]["id"]
