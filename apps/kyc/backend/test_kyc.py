"""Phase 2 tests: four-eyes rule, reason codes, PII unmask auditing."""
import importlib

import httpx

import pytest
from fastapi.testclient import TestClient



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


def open_case_id(client: TestClient, headers: dict, high_risk: bool = False) -> int:
    cases = client.get("/api/kyc/cases?status=open", headers=headers).json()
    for c in cases:
        if (c["risk_score"] >= 70) == high_risk:
            return c["id"]
    pytest.fail("no matching open case")


def _kyc(module: str):
    """This app's modules, as mounted by app.main (package portal_apps.kyc)."""
    import app.main  # noqa: F401  (mounts apps/*)

    return importlib.import_module(f"portal_apps.kyc.{module}")


class TestEscalatorRule:
    def test_escalator_cannot_decide(self, client):
        h = login(client, "rana")
        cid = open_case_id(client, h)
        res = client.post(f"/api/kyc/cases/{cid}/escalate", headers=h,
                          json={"reason_code": "high_risk_score"})
        assert res.status_code == 200, res.text
        # Same user now gets a specific 403 — not a generic status conflict.
        res = client.post(f"/api/kyc/cases/{cid}/approve", headers=h)
        assert res.status_code == 403
        assert "escalated" in res.json()["detail"]
        res = client.post(f"/api/kyc/cases/{cid}/reject", headers=h,
                          json={"reason_code": "other"})
        assert res.status_code == 403

    def test_admin_can_decide_escalated(self, client):
        h = login(client, "rana")
        cid = open_case_id(client, h)
        client.post(f"/api/kyc/cases/{cid}/escalate", headers=h,
                    json={"reason_code": "sanctions_hit"})
        # Admin senior-review on the escalated case still works.
        res = client.post(f"/api/kyc/cases/{cid}/approve",
                          headers=login(client, "priya"))
        assert res.status_code == 200, res.text

    def test_escalation_is_audited(self, client):
        h = login(client, "rana")
        cid = open_case_id(client, h)
        client.post(f"/api/kyc/cases/{cid}/escalate", headers=h,
                    json={"reason_code": "pep_hit"})
        entries = client.get("/api/audit", headers=login(client, "priya")).json()
        esc = [e for e in entries if e["action"] == "kyc.escalate" and e["entity_id"] == str(cid)]
        assert esc and esc[0]["actor"] == "rana"


# --------------------------------------------------------------------------
# Repository contract tests — same assertions against both adapters.
# --------------------------------------------------------------------------

def _contract(repo):
    """Every adapter must satisfy this contract."""
    cases = repo.list_cases()
    assert cases, "repository returned no cases"
    cid = next(c["id"] for c in cases if c["status"] == "open")
    case = repo.get_case(cid)
    assert case and case["id"] == cid
    assert "applicant_name" in case and "approvals" in case
    with repo.transaction() as tx:
        assert not repo.has_escalated(tx, cid, "tester")
        repo.add_escalation(tx, cid, "tester", "other")
        assert repo.has_escalated(tx, cid, "tester")
        repo.update_case(tx, cid, {"status": "rejected"})
        repo.write_audit(
            tx, actor="tester", action="kyc.reject",
            entity="kyc_case", entity_id=cid,
        )
    assert repo.get_case(cid)["status"] == "rejected"


def test_contract_sql_adapter(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTAL_DB_PATH", str(tmp_path / "sqlrepo.db"))
    import app.db

    importlib.reload(app.db)
    domain = _kyc("domain")
    app.db.init_db()
    with app.db.get_db() as conn:
        domain.seed_kyc(conn)
    SqlKycRepository = _kyc("repository").SqlKycRepository

    _contract(SqlKycRepository())


class _DvStore:
    """In-memory OData endpoint backing the Dataverse adapter tests."""

    def __init__(self):
        self.cases = {
            7: {
                "mer_kyccaseid": "guid-7", "mer_caseid": 7,
                "mer_applicantname": "Ada Osei", "mer_dob": "1990-01-01",
                "mer_email": "ada@example.com", "mer_phone": "+1234567",
                "mer_address": "1 Test St", "mer_nationalid": "NID-1",
                "mer_country": "Ghana", "mer_status": "open",
                "mer_riskscore": 30, "mer_assignee": None,
                "mer_createdon": "2026-10-20 00:00:00",
            }
        }
        self.escalations: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        q = request.url.params
        if path.endswith("/oauth2/v2.0/token"):
            return httpx.Response(200, json={
                "access_token": "dv-token", "expires_in": 3600,
            })
        if "mer_kyccases" in path:
            if request.method == "PATCH":
                import json as _j

                row = next(iter(self.cases.values()))
                row.update(_j.loads(request.content or b"{}"))
                return httpx.Response(200, json=row)
            # GET with $filter mer_caseid eq N
            filt = q.get("$filter", "")
            rows = list(self.cases.values())
            if "mer_caseid eq" in filt:
                cid = int(filt.split("mer_caseid eq")[1].strip().split()[0])
                rows = [r for r in rows if r["mer_caseid"] == cid]
            return httpx.Response(200, json={"value": rows})
        if "mer_kycescalations" in path:
            if request.method == "POST":
                import json as _j

                self.escalations.append(_j.loads(request.content or b"{}"))
                return httpx.Response(201, json={})
            filt = q.get("$filter", "")
            out = self.escalations
            if "mer_actor eq" in filt:
                actor = filt.split("mer_actor eq")[1].strip().strip("'")
                out = [e for e in out if e["mer_actor"] == actor]
            return httpx.Response(200, json={
                "value": [{"mer_kycescalationid": "e1"} for _ in out],
            })
        if "mer_kycapprovals" in path:
            return httpx.Response(200, json={"value": []})
        return httpx.Response(404, json={"error": path})


def test_contract_dataverse_adapter(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTAL_DB_PATH", str(tmp_path / "dvaudit.db"))
    import app.db

    importlib.reload(app.db)
    app.db.init_db()
    import portal_platform.config as cfg

    monkeypatch.setattr(cfg, "DATAVERSE_BASE_URL", "https://org.crm.example")
    monkeypatch.setattr(cfg, "DATAVERSE_TOKEN_URL",
                        "https://org.crm.example/oauth2/v2.0/token")
    store = _DvStore()
    DataverseKycRepository = _kyc("dataverse_repo").DataverseKycRepository

    repo = DataverseKycRepository(
        client=httpx.Client(transport=httpx.MockTransport(store.handler))
    )
    _contract(repo)
    assert store.escalations and store.escalations[0]["mer_actor"] == "tester"
