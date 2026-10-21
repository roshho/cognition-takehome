"""Phase 3 tests: refund threshold enforcement, flag toggles + history."""
import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTAL_DB_PATH", str(tmp_path / "test.db"))
    import app.db

    importlib.reload(app.db)
    import app.auth
    import app.routers.auth, app.routers.me, app.routers.core
    import app.routers.kyc, app.routers.refunds, app.routers.flags, app.main

    for m in (app.auth, app.routers.auth, app.routers.me, app.routers.core,
              app.routers.kyc, app.routers.refunds, app.routers.flags, app.main):
        importlib.reload(m)
    with TestClient(app.main.app) as c:
        yield c


def login(client: TestClient, username: str) -> dict:
    res = client.post("/api/auth/login", json={"username": username})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


def pending(client: TestClient, headers: dict, requires_admin: bool) -> dict:
    refunds = client.get("/api/refunds?status=pending", headers=headers).json()
    return next(r for r in refunds if r["requires_admin"] is requires_admin)


class TestRefundThreshold:
    def test_reviewer_can_approve_small_refund(self, client):
        rana = login(client, "rana")
        r = pending(client, rana, requires_admin=False)
        res = client.post(f"/api/refunds/{r['id']}/approve", json={}, headers=rana)
        assert res.status_code == 200
        assert res.json()["status"] == "approved"

    def test_reviewer_cannot_decide_over_threshold(self, client):
        rana = login(client, "rana")
        r = pending(client, rana, requires_admin=True)
        for action in ("approve", "deny"):
            res = client.post(f"/api/refunds/{r['id']}/{action}", json={}, headers=rana)
            assert res.status_code == 403

    def test_admin_can_decide_over_threshold(self, client):
        priya = login(client, "priya")
        r = pending(client, priya, requires_admin=True)
        res = client.post(f"/api/refunds/{r['id']}/deny", json={}, headers=priya)
        assert res.status_code == 200
        # closed refunds can't be decided again
        res = client.post(f"/api/refunds/{r['id']}/approve", json={}, headers=priya)
        assert res.status_code == 409

    def test_refund_decisions_are_audited(self, client):
        rana = login(client, "rana")
        r = pending(client, rana, requires_admin=False)
        client.post(f"/api/refunds/{r['id']}/approve",
                    json={"reason": "duplicate_charge"}, headers=rana)
        entries = client.get("/api/audit", headers=rana).json()
        entry = next(e for e in entries if e["action"] == "refund.approve"
                     and e["entity_id"] == str(r["id"]))
        assert '"pending"' in entry["before"] and '"approved"' in entry["after"]


class TestFlags:
    def test_toggle_dev_and_staging_open_to_reviewers(self, client):
        rana = login(client, "rana")
        before = client.get("/api/flags", headers=rana).json()
        flag = next(f for f in before if not f["enabled_dev"])
        res = client.post(f"/api/flags/{flag['key']}/toggle",
                          json={"environment": "dev"}, headers=rana)
        assert res.status_code == 200
        assert res.json()["enabled_dev"] is True

    def test_prod_toggle_requires_admin(self, client):
        rana, priya = login(client, "rana"), login(client, "priya")
        res = client.post("/api/flags/export_csv/toggle",
                          json={"environment": "prod"}, headers=rana)
        assert res.status_code == 403
        res = client.post("/api/flags/export_csv/toggle",
                          json={"environment": "prod"}, headers=priya)
        assert res.status_code == 200
        assert res.json()["enabled_prod"] is True

    def test_bad_environment_is_422(self, client):
        rana = login(client, "rana")
        res = client.post("/api/flags/dark_mode/toggle",
                          json={"environment": "canary"}, headers=rana)
        assert res.status_code == 422

    def test_history_comes_from_audit_log(self, client):
        rana = login(client, "rana")
        client.post("/api/flags/export_csv/toggle",
                    json={"environment": "dev"}, headers=rana)
        history = client.get("/api/flags/export_csv/history", headers=rana).json()
        assert len(history) == 1
        entry = history[0]
        assert entry["action"] == "flag.toggle" and entry["actor"] == "rana"
        assert '"dev": false' in entry["before"]
        assert '"dev": true' in entry["after"]
