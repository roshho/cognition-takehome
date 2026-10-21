"""Production-shape tests: RBAC 403s, escalator rule, audit hardening,
repository contract (SQL + mocked-HTTP Dataverse), mock OIDC chain."""
import importlib
import os
import sqlite3
import sys
import time
from pathlib import Path

import httpx
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
    import portal_platform.adapters

    for m in (app.auth, app.routers.auth, app.routers.me, app.routers.core,
              app.routers.kyc, app.routers.refunds, app.routers.flags, app.main):
        importlib.reload(m)
    importlib.reload(portal_platform.adapters)
    portal_platform.adapters._reset_for_tests()
    with TestClient(app.main.app) as c:
        yield c


def login(client: TestClient, username: str) -> dict:
    res = client.post("/api/auth/login", json={"username": username})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


def open_case_id(client: TestClient, headers: dict, high_risk: bool = False) -> int:
    cases = client.get("/api/kyc/cases?status=open", headers=headers).json()
    for c in cases:
        if (c["risk_score"] >= 70) == high_risk:
            return c["id"]
    pytest.fail("no matching open case")


class TestReadOnlyRole:
    def test_read_only_can_view(self, client):
        h = login(client, "marco")
        assert client.get("/api/kyc/cases", headers=h).status_code == 200
        cid = open_case_id(client, h)
        assert client.get(f"/api/kyc/cases/{cid}", headers=h).status_code == 200
        assert client.get("/api/refunds", headers=h).status_code == 200
        assert client.get("/api/flags", headers=h).status_code == 200
        assert client.get("/api/audit", headers=h).status_code == 200

    def test_read_only_denied_every_mutation(self, client):
        h = login(client, "marco")
        cid = open_case_id(client, h)
        rid = client.get("/api/refunds?status=pending", headers=h).json()[0]["id"]
        key = client.get("/api/flags", headers=h).json()[0]["key"]
        assert client.post(f"/api/kyc/cases/{cid}/approve", headers=h).status_code == 403
        assert client.post(f"/api/kyc/cases/{cid}/assign", headers=h).status_code == 403
        assert client.post(f"/api/kyc/cases/{cid}/unmask", headers=h).status_code == 403
        assert client.post(
            f"/api/kyc/cases/{cid}/reject", headers=h,
            json={"reason_code": "document_mismatch"},
        ).status_code == 403
        assert client.post(f"/api/kyc/cases/{cid}/escalate", headers=h,
                           json={"reason_code": "sanctions_hit"}).status_code == 403
        assert client.post(f"/api/kyc/cases/{cid}/notes", headers=h,
                           json={"body": "x"}).status_code == 403
        assert client.post(f"/api/refunds/{rid}/approve", headers=h).status_code == 403
        assert client.post(f"/api/refunds/{rid}/deny", headers=h).status_code == 403
        assert client.post(f"/api/flags/{key}/toggle", headers=h,
                           json={"environment": "dev"}).status_code == 403
        assert client.get("/api/users", headers=h).status_code == 403


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


class TestAuditHardening:
    def test_request_id_is_recorded(self, client):
        h = login(client, "rana")
        cid = open_case_id(client, h)
        res = client.post(f"/api/kyc/cases/{cid}/unmask", headers=h)
        assert res.headers.get("x-request-id")
        entries = client.get("/api/audit", headers=login(client, "priya")).json()
        unmask = next(e for e in entries if e["action"] == "kyc.unmask_pii")
        assert unmask["request_id"] == res.headers["x-request-id"]

    def test_audit_table_rejects_update_and_delete(self, tmp_path):
        import app.db

        db = tmp_path / "a.db"
        app.db.init_db(db)
        conn = app.db.connect(db)
        conn.execute(
            "INSERT INTO audit_log (actor, action, entity) VALUES ('x', 'a', 'e')"
        )
        conn.commit()
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("UPDATE audit_log SET actor='y'")
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("DELETE FROM audit_log")
        # inserts still work
        conn.execute(
            "INSERT INTO audit_log (actor, action, entity) VALUES ('x', 'a', 'e')"
        )
        conn.commit()
        conn.close()


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
    import app.kyc

    importlib.reload(app.db)
    app.db.init_db()
    with app.db.get_db() as conn:
        app.kyc.seed_kyc(conn)
    from portal_platform.adapters.sqlite_repo import SqlKycRepository

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
    from portal_platform.adapters.dataverse_repo import DataverseKycRepository

    repo = DataverseKycRepository(
        client=httpx.Client(transport=httpx.MockTransport(store.handler))
    )
    _contract(repo)
    assert store.escalations and store.escalations[0]["mer_actor"] == "tester"


# --------------------------------------------------------------------------
# OIDC — group->role mapping and the mock IdP's signed-token chain.
# --------------------------------------------------------------------------

class TestOidc:
    def test_group_role_mapping(self):
        from portal_platform.rbac import role_for_groups

        assert role_for_groups(["kyc_admin"]) == "admin"
        assert role_for_groups(["kyc_reviewer"]) == "reviewer"
        assert role_for_groups(["read_only"]) == "read_only"
        assert role_for_groups(["unmapped"]) == "read_only"
        assert role_for_groups([]) == "read_only"

    def test_mock_idp_issues_verifiable_tokens(self):
        from fastapi.testclient import TestClient
        from jwt import PyJWKClient  # noqa: F401
        from jwt.algorithms import RSAAlgorithm
        import jwt as pyjwt

        os.environ["IDP_ISSUER"] = "http://idp.test"
        import mockidp.app as idp

        c = TestClient(idp.app)
        res = c.get(
            "/authorize",
            params={
                "client_id": "portal",
                "redirect_uri": "http://portal/cb",
                "response_type": "code",
                "state": "s1",
                "user": "priya",
            },
            follow_redirects=False,
        )
        assert res.status_code in (302, 307)
        loc = res.headers["location"]
        code = loc.split("code=")[1].split("&")[0]
        assert "state=s1" in loc
        tok = c.post("/token", data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": "portal",
            "redirect_uri": "http://portal/cb",
        }).json()
        jwk = c.get("/jwks").json()["keys"][0]
        key = RSAAlgorithm.from_jwk(jwk)
        claims = pyjwt.decode(
            tok["id_token"], key, algorithms=["RS256"],
            audience="portal", issuer="http://idp.test",
        )
        assert claims["preferred_username"] == "priya"
        assert claims["groups"] == ["kyc_admin"]
        del os.environ["IDP_ISSUER"]
