"""Phase 1 tests: role enforcement and audit logging."""
import importlib
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTAL_DB_PATH", str(tmp_path / "test.db"))
    import app.db

    importlib.reload(app.db)  # re-read PORTAL_DB_PATH
    import app.auth, app.routers.auth, app.routers.me, app.routers.core, app.main

    importlib.reload(app.auth)
    importlib.reload(app.routers.auth)
    importlib.reload(app.routers.me)
    importlib.reload(app.routers.core)
    importlib.reload(app.main)
    with TestClient(app.main.app) as c:
        yield c


def login(client: TestClient, username: str) -> dict:
    res = client.post("/api/auth/login", json={"username": username})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


class TestRoleEnforcement:
    def test_unauthenticated_is_401(self, client):
        assert client.get("/api/users").status_code == 401
        assert client.get("/api/me").status_code == 401

    def test_reviewer_cannot_list_users(self, client):
        headers = login(client, "rana")
        res = client.get("/api/users", headers=headers)
        assert res.status_code == 403

    def test_admin_can_list_users(self, client):
        headers = login(client, "priya")
        res = client.get("/api/users", headers=headers)
        assert res.status_code == 200
        assert {u["username"] for u in res.json()} == {"rana", "kwon", "priya"}

    def test_tools_are_filtered_by_role(self, client):
        reviewer_tools = client.get("/api/tools", headers=login(client, "rana")).json()
        admin_tools = client.get("/api/tools", headers=login(client, "priya")).json()
        assert {t["id"] for t in reviewer_tools} == {
            "audit-trail", "kyc-queue", "refunds", "feature-flags"}
        assert {t["id"] for t in admin_tools} == {
            "directory", "audit-trail", "kyc-queue", "refunds", "feature-flags"}

    def test_bad_token_is_401(self, client):
        assert client.get("/api/me", headers={"Authorization": "Bearer nope"}).status_code == 401


class TestAuditLog:
    def test_login_is_audited(self, client):
        headers = login(client, "rana")
        entries = client.get("/api/audit", headers=headers).json()
        assert any(e["action"] == "auth.login" and e["actor"] == "rana" for e in entries)

    def test_mutation_writes_before_and_after(self, client):
        headers = login(client, "rana")
        res = client.patch("/api/me", json={"display_name": "Rana A."}, headers=headers)
        assert res.status_code == 200
        entries = client.get("/api/audit", headers=headers).json()
        update = next(e for e in entries if e["action"] == "user.update_display_name")
        assert update["actor"] == "rana"
        assert update["entity"] == "user"
        assert '"Rana Alvarez"' in update["before"]
        assert '"Rana A."' in update["after"]

    def test_audit_is_append_only_and_role_scoped(self, client):
        login(client, "rana")
        reviewer_entries = client.get("/api/audit", headers=login(client, "rana")).json()
        admin_entries = client.get("/api/audit", headers=login(client, "priya")).json()
        # reviewer only sees own actions
        assert all(e["actor"] == "rana" for e in reviewer_entries)
        # admin sees everything, including rana's
        actors = {e["actor"] for e in admin_entries}
        assert "rana" in actors and "priya" in actors
