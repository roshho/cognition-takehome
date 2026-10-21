"""Shared pytest fixtures for backend/tests and apps/*/backend tests.

``client``: a TestClient over a fresh temp SQLite DB with every app under
apps/ re-mounted. ``login("rana")`` -> Authorization headers.
"""
import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTAL_DB_PATH", str(tmp_path / "test.db"))
    import app.db

    importlib.reload(app.db)  # re-read PORTAL_DB_PATH
    import portal_platform.repository

    portal_platform.repository._reset_for_tests()
    import app.main

    importlib.reload(app.main)  # re-mounts apps/* (fresh modules + registrations)
    with TestClient(app.main.app) as c:
        yield c


@pytest.fixture()
def login(client: TestClient):
    def _login(username: str) -> dict:
        res = client.post("/api/auth/login", json={"username": username})
        assert res.status_code == 200, res.text
        return {"Authorization": f"Bearer {res.json()['token']}"}

    return _login
