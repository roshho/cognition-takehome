"""Phase 2 tests: four-eyes rule, reason codes, PII unmask auditing."""
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
    import app.auth, app.routers.auth, app.routers.me, app.routers.core
    import app.routers.kyc, app.main

    for m in (app.auth, app.routers.auth, app.routers.me, app.routers.core,
              app.routers.kyc, app.main):
        importlib.reload(m)
    with TestClient(app.main.app) as c:
        yield c


def login(client: TestClient, username: str) -> dict:
    res = client.post("/api/auth/login", json={"username": username})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


def first_case(client: TestClient, headers: dict, risk_level: str) -> dict:
    cases = client.get("/api/kyc/cases", headers=headers).json()
    return next(c for c in cases if c["risk_level"] == risk_level and c["status"] == "open")


class TestFourEyes:
    def test_high_risk_needs_two_distinct_approvers(self, client):
        rana, kwon = login(client, "rana"), login(client, "kwon")
        case = first_case(client, rana, "high")
        assert case["approvals_required"] == 2

        res = client.post(f"/api/kyc/cases/{case['id']}/approve", headers=rana)
        assert res.status_code == 200
        assert res.json()["status"] == "open"
        assert res.json()["awaiting_second_reviewer"] is True

        # nobody approves their own decision — second vote by same user fails
        res = client.post(f"/api/kyc/cases/{case['id']}/approve", headers=rana)
        assert res.status_code == 409

        # a different reviewer completes the four-eyes check
        res = client.post(f"/api/kyc/cases/{case['id']}/approve", headers=kwon)
        assert res.status_code == 200
        assert res.json()["status"] == "approved"

    def test_low_risk_single_approval(self, client):
        rana = login(client, "rana")
        case = first_case(client, rana, "low")
        res = client.post(f"/api/kyc/cases/{case['id']}/approve", headers=rana)
        assert res.json()["status"] == "approved"
        assert res.json()["approvals_required"] == 1


class TestDecisions:
    def test_reject_and_escalate_need_reason_code(self, client):
        rana = login(client, "rana")
        case = first_case(client, rana, "medium")
        for action in ("reject", "escalate"):
            res = client.post(f"/api/kyc/cases/{case['id']}/{action}",
                              json={"reason_code": ""}, headers=rana)
            assert res.status_code == 422
            res = client.post(f"/api/kyc/cases/{case['id']}/{action}",
                              json={"reason_code": "bogus"}, headers=rana)
            assert res.status_code == 422

    def test_reject_with_reason_closes_case_and_audits(self, client):
        rana = login(client, "rana")
        case = first_case(client, rana, "low")
        res = client.post(f"/api/kyc/cases/{case['id']}/reject",
                          json={"reason_code": "document_mismatch"}, headers=rana)
        assert res.status_code == 200
        # closed case can't be actioned again
        res = client.post(f"/api/kyc/cases/{case['id']}/approve", headers=rana)
        assert res.status_code == 409
        entries = client.get("/api/audit", headers=rana).json()
        entry = next(e for e in entries if e["action"] == "kyc.reject"
                     and e["entity_id"] == str(case["id"]))
        assert '"document_mismatch"' in entry["after"]

    def test_assign_is_audited(self, client):
        rana = login(client, "rana")
        case = first_case(client, rana, "medium")
        res = client.post(f"/api/kyc/cases/{case['id']}/assign", headers=rana)
        assert res.status_code == 200
        entries = client.get("/api/audit", headers=rana).json()
        assert any(e["action"] == "kyc.assign" and e["entity_id"] == str(case["id"])
                   for e in entries)


class TestPiiMasking:
    def test_detail_masks_pii_and_unmask_is_audited(self, client):
        rana = login(client, "rana")
        case = first_case(client, rana, "low")
        detail = client.get(f"/api/kyc/cases/{case['id']}", headers=rana).json()
        assert "•" in detail["email"]
        assert detail["address"].startswith("•")

        res = client.post(f"/api/kyc/cases/{case['id']}/unmask", headers=rana)
        assert res.status_code == 200
        assert "@" in res.json()["email"] and "•" not in res.json()["email"]

        entries = client.get("/api/audit", headers=rana).json()
        assert any(e["action"] == "kyc.unmask_pii" and e["entity_id"] == str(case["id"])
                   for e in entries)

    def test_kyc_requires_authentication(self, client):
        assert client.get("/api/kyc/cases").status_code == 401
