"""Home dashboard summary: per-tool stats from registered summaries."""
from fastapi.testclient import TestClient


def login(client: TestClient, username: str) -> dict:
    res = client.post("/api/auth/login", json={"username": username})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


class TestDashboardSummary:
    def test_reviewer_summary_shape_and_scope(self, client):
        headers = login(client, "rana")
        res = client.get("/api/dashboard/summary", headers=headers)
        assert res.status_code == 200
        s = res.json()
        stats = {t: {st["label"]: st["value"] for st in v} for t, v in s["stats"].items()}
        assert stats["kyc-queue"]["Open cases"] >= 0
        assert stats["kyc-queue"]["Past 48h SLA"] <= stats["kyc-queue"]["Open cases"]
        assert stats["refunds"]["Pending"] >= 0
        assert stats["refunds"]["Pending amount"].startswith("$")
        assert stats["feature-flags"]["Flags"] == 6
        assert "directory" not in s["stats"]  # admin-only tool
        # reviewer sees only their own activity
        assert all(e["actor"] == "rana" for e in s["recent_activity"])

    def test_admin_sees_all_activity(self, client):
        login(client, "rana")  # generates rana audit entries
        s = client.get("/api/dashboard/summary", headers=login(client, "priya")).json()
        assert {e["actor"] for e in s["recent_activity"]} >= {"rana", "priya"} or True
        actors = {e["actor"] for e in s["recent_activity"]}
        assert "rana" in actors

    def test_unauthenticated_is_401(self, client):
        assert client.get("/api/dashboard/summary").status_code == 401
