"""Production-shape tests: RBAC 403s, escalator rule, audit hardening,
repository contract (SQL + mocked-HTTP Dataverse), mock OIDC chain."""
import os
import sqlite3

import pytest
from fastapi.testclient import TestClient


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
# Adapter registry — per-app selection via config.
# --------------------------------------------------------------------------

class TestAdapterSelection:
    def test_per_app_and_global_selection(self, monkeypatch):
        from portal_platform import repository as r

        monkeypatch.setattr(r, "_FACTORIES", {})
        monkeypatch.setattr(r, "_INSTANCES", {})
        r.register_adapter("a", "sql", lambda: "a-sql")
        r.register_adapter("a", "dataverse", lambda: "a-dv")
        r.register_adapter("b", "sql", lambda: "b-sql")
        monkeypatch.setenv("DATA_ADAPTER", "dataverse")
        # global applies where available, others stay on sql
        assert r.get_repository("a") == "a-dv"
        assert r.get_repository("b") == "b-sql"
        # explicit per-app kind must exist
        r._reset_for_tests()
        monkeypatch.setenv("DATA_ADAPTER_B", "dataverse")
        with pytest.raises(RuntimeError):
            r.get_repository("b")

    def test_every_mounted_app_resolves_an_adapter(self, client):
        from portal_platform import repository as r

        for app_name in ("kyc", "refunds", "flags", "it-assets"):
            assert r.get_repository(app_name) is not None


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
