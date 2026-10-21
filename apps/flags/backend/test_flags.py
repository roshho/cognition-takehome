"""Feature-flag app tests: env toggles, prod gate, history, repository contract."""
from fastapi.testclient import TestClient


def login(client: TestClient, username: str) -> dict:
    res = client.post("/api/auth/login", json={"username": username})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


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


class TestFlagsRepository:
    def test_contract(self, client):
        import importlib

        repo = importlib.import_module("portal_apps.flags.repository").SqlFlagsRepository()
        flags = repo.list()
        assert len(flags) == 6 and isinstance(flags[0]["enabled_dev"], bool)
        with repo.transaction() as tx:
            repo.update(tx, "export_csv", {"enabled_dev": 1})
            repo.write_audit(tx, actor="tester", action="flag.toggle",
                             entity="feature_flag", entity_id="export_csv")
        assert repo.get("export_csv")["enabled_dev"] is True
        assert repo.audit_history("feature_flag", "export_csv")[0]["actor"] == "tester"
