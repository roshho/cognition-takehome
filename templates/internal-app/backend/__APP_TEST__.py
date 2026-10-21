"""Contract tests for __APP_TITLE__: role denial + audit writes.

Uses the `client` and `login` fixtures from apps/conftest.py.
Conventions these verify (AGENTS.md): read_only is denied writes (403),
and every mutation lands an audit row with before/after.
"""


class Test__APP_CLASS__:
    APP = "__APP__"
    TABLE = "__APP_TABLE__"

    def test_read_only_can_list_but_not_write(self, client, login):
        ro = login("marco")
        assert client.get(f"/api/{self.APP}/items", headers=ro).status_code == 200
        res = client.post(f"/api/{self.APP}/items", json={"name": "x"}, headers=ro)
        assert res.status_code == 403

    def test_create_and_close_are_audited(self, client, login):
        h = login("rana")
        res = client.post(f"/api/{self.APP}/items", json={"name": "widget"}, headers=h)
        assert res.status_code == 201, res.text
        item_id = res.json()["id"]

        res = client.post(f"/api/{self.APP}/items/{item_id}/close", headers=h)
        assert res.status_code == 200, res.text
        assert res.json()["status"] == "closed"

        audit = client.get("/api/audit", headers=login("priya")).json()
        create = next(e for e in audit if e["action"] == f"{self.APP}.create")
        close = next(e for e in audit if e["action"] == f"{self.APP}.close")
        assert create["entity"] == self.TABLE and str(create["entity_id"]) == str(item_id)
        assert "open" in close["before"]
        assert "closed" in close["after"]

    def test_input_validation(self, client, login):
        h = login("rana")
        res = client.post(f"/api/{self.APP}/items", json={"name": ""}, headers=h)
        assert res.status_code == 422
