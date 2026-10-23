"""Tests run against a throwaway data directory (fresh SQLite DB, freshly trained models)."""

import os
import shutil
import tempfile
import uuid
from pathlib import Path

import pytest

_DATA = Path(tempfile.mkdtemp(prefix="finpilot-test-"))
os.environ["FINPILOT_DATA_DIR"] = str(_DATA)
os.environ["FINPILOT_TESTING"] = "1"
os.environ["FINPILOT_SCHEDULER"] = "0"


@pytest.fixture(scope="session", autouse=True)
def _db():
    from app.db.migrate import run_migrations

    run_migrations()
    from app.db.session import session_scope
    from app.services.reference_data import ensure_reference_data

    with session_scope() as db:  # as at server start: every test file can run on its own
        ensure_reference_data(db)
    import app.jobs.tasks  # noqa: F401  (jobs run inline in tests)

    yield
    from app.db.session import dispose_engine

    dispose_engine()
    shutil.rmtree(_DATA, ignore_errors=True)


@pytest.fixture(scope="session")
def demo(_db):
    from app.services.demo import ensure_demo

    return ensure_demo()


@pytest.fixture
def client(_db):
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as c:
        c.headers.update({"X-Requested-With": "finpilot"})
        yield c


@pytest.fixture
def demo_client(client, demo):
    assert client.post("/api/v1/auth/demo").status_code == 200
    return client


@pytest.fixture
def new_user(client):
    email = f"u{uuid.uuid4().hex[:8]}@test.dev"
    r = client.post("/api/v1/auth/register", json={"name": "Test User", "email": email, "password": "secret123"})
    assert r.status_code == 200, r.text
    return client


@pytest.fixture
def phone():
    """A client that behaves like the Android app: no cookies, Bearer tokens, cross-origin WebView requests."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as c:
        c.headers.update({"Origin": "http://localhost", "X-FinPilot-Client": "android"})
        yield c


def sign_up_phone(phone, name: str = "Priya Raman") -> dict:
    email = f"p{uuid.uuid4().hex[:8]}@test.dev"
    r = phone.post("/api/v1/auth/register", json={"name": name, "email": email, "password": "secret123"})
    assert r.status_code == 200, r.text
    tokens = r.json()
    phone.cookies.clear()
    phone.headers["Authorization"] = f"Bearer {tokens['access_token']}"
    return tokens
