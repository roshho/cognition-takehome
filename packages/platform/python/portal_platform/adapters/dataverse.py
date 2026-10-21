"""Dataverse adapter base — OData Web API plumbing shared by app adapters.

Auth is OAuth2 client-credentials via env vars (DATAVERSE_TENANT_ID /
CLIENT_ID / CLIENT_SECRET, token URL overridable for non-Microsoft IdPs).
There is no ambient transaction in OData: ``transaction()`` returns a shim
and audit rows go to the local append-only audit table — in production
this needs an ExecuteTransaction batch or an outbox (see README known gaps).

Only exercised in tests via an injected httpx.Client/transport; nothing
here has been run against a real Dataverse environment.
"""
import time
from contextlib import contextmanager

import httpx

from .. import config
from ..audit import write_audit as _write_audit


class DataverseTx:
    """No ambient transaction — carries the local audit connection."""

    def __init__(self):
        self._audit_conn = None

    def audit_conn(self):
        if self._audit_conn is None:
            from app.db import DB_PATH, connect

            self._audit_conn = connect(DB_PATH)
        return self._audit_conn

    def close(self):
        if self._audit_conn is not None:
            self._audit_conn.commit()
            self._audit_conn.close()
            self._audit_conn = None


class DataverseClient:
    def __init__(self, client: httpx.Client | None = None, entity: str | None = None):
        self._http = client or httpx.Client(timeout=15.0)
        self._base = config.DATAVERSE_BASE_URL
        self._entity = entity or config.DATAVERSE_ENTITY
        self._token: str | None = None
        self._token_exp = 0.0

    # --- auth ---
    def _access_token(self) -> str:
        if self._token and time.time() < self._token_exp - 30:
            return self._token
        res = self._http.post(
            config.DATAVERSE_TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": config.DATAVERSE_CLIENT_ID,
                "client_secret": config.DATAVERSE_CLIENT_SECRET,
                "scope": f"{self._base}/.default",
            },
        )
        res.raise_for_status()
        body = res.json()
        self._token = body["access_token"]
        self._token_exp = time.time() + float(body.get("expires_in", 3600))
        return self._token

    # --- OData plumbing ---
    def _url(self, collection: str, extra: str = "") -> str:
        return f"{self._base}/{config.DATAVERSE_API}/{collection}{extra}"

    def _req(self, method: str, url: str, **kw) -> httpx.Response:
        res = self._http.request(
            method,
            url,
            headers={
                "Authorization": f"Bearer {self._access_token()}",
                "OData-MaxVersion": "4.0",
                "OData-Version": "4.0",
                "Accept": "application/json",
                "Content-Type": "application/json; charset=utf-8",
                "Prefer": "return=representation",
            },
            **kw,
        )
        res.raise_for_status()
        return res

    def _query(self, collection: str, filt: str = "", select: str = "") -> list[dict]:
        params = {}
        if filt:
            params["$filter"] = filt
        if select:
            params["$select"] = select
        res = self._req("GET", self._url(collection), params=params)
        return res.json().get("value", [])

    # --- transaction + audit ---
    @contextmanager
    def transaction(self):
        tx = DataverseTx()
        try:
            yield tx
        finally:
            tx.close()

    def write_audit(self, tx, **kw):
        _write_audit(tx.audit_conn(), **kw)
