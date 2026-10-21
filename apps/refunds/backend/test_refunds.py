"""Refunds app tests: admin threshold, audit, repository contract."""
import pytest
from fastapi.testclient import TestClient


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


class TestRefundsRepository:
    """SQL adapter contract: list/get/update + audit in one transaction."""

    def test_contract(self, client):
        import importlib

        repo = importlib.import_module("portal_apps.refunds.repository").SqlRefundsRepository()
        pending = repo.list(status="pending")
        assert pending and all(r["status"] == "pending" for r in pending)
        assert all(r["amount_cents"] >= 100_000 for r in repo.list(min_amount=100_000))
        rid = pending[0]["id"]
        with repo.transaction() as tx:
            repo.update(tx, rid, {"status": "denied", "decided_by": "tester"})
            repo.write_audit(tx, actor="tester", action="refund.deny",
                             entity="refund", entity_id=rid)
        assert repo.get(rid)["status"] == "denied"
        assert repo.get(10**9) is None

    def test_rejects_unknown_columns(self, client):
        import importlib


        repo = importlib.import_module("portal_apps.refunds.repository").SqlRefundsRepository()
        with repo.transaction() as tx, pytest.raises(ValueError):
            repo.update(tx, 1, {"id; DROP TABLE refunds": 1})

