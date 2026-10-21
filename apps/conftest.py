"""Pytest glue for generated apps under apps/*/backend/test_*.py.

Run from backend/: `.venv/bin/python -m pytest tests ../apps -q`.
Adds backend/ to sys.path so app tests can import `app` and
`portal_platform`, and provides the same tmp-db client fixture +
login helper the built-in test suite uses.
"""
import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTAL_DB_PATH", str(tmp_path / "test.db"))
    import app.db

    importlib.reload(app.db)
    import app.auth
    import app.routers.auth, app.routers.me, app.routers.core
    import app.routers.kyc, app.routers.refunds, app.routers.flags, app.main
    import portal_platform.adapters

    for m in (app.auth, app.routers.auth, app.routers.me, app.routers.core,
              app.routers.kyc, app.routers.refunds, app.routers.flags, app.main):
        importlib.reload(m)
    importlib.reload(portal_platform.adapters)
    portal_platform.adapters._reset_for_tests()
    with TestClient(app.main.app) as c:
        yield c


@pytest.fixture()
def login(client: TestClient):
    """login("rana") -> {"Authorization": "Bearer ..."} headers dict."""
    def _login(username: str) -> dict:
        res = client.post("/api/auth/login", json={"username": username})
        assert res.status_code == 200, res.text
        return {"Authorization": f"Bearer {res.json()['token']}"}

    return _login
