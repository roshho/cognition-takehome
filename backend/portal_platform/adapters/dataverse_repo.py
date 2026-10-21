"""Dataverse adapter — KYC case store over the OData Web API.

Auth is OAuth2 client-credentials via env vars (DATAVERSE_TENANT_ID /
CLIENT_ID / CLIENT_SECRET, token URL overridable for non-Microsoft IdPs).
There is no ambient transaction in OData: ``transaction()`` returns a shim
and audit rows go to the local append-only audit table *after* the remote
call commits — in production this needs an outbox (see README known gaps).

Only reachable in tests via an injected httpx.Client/transport; nothing
here has been run against a real Dataverse environment.
"""
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import httpx

from .. import config
from ..audit import write_audit as _write_audit

_STATUS = ("open", "approved", "rejected", "escalated")


def _parse_dt(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


class _DvTx:
    """No ambient transaction — carries the local audit connection."""

    def __init__(self):
        self._audit_conn = None

    def audit_conn(self):
        if self._audit_conn is None:
            from app.db import connect, DB_PATH

            self._audit_conn = connect(DB_PATH)
        return self._audit_conn

    def close(self):
        if self._audit_conn is not None:
            self._audit_conn.commit()
            self._audit_conn.close()
            self._audit_conn = None


class DataverseKycRepository:
    def __init__(self, client: httpx.Client | None = None):
        self._http = client or httpx.Client(timeout=15.0)
        self._base = config.DATAVERSE_BASE_URL
        self._entity = config.DATAVERSE_ENTITY
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

    # --- field mapping ---
    @staticmethod
    def _to_record(v: dict) -> dict:
        from app.kyc import required_approvals, risk_level, SLA_HOURS

        created = v.get("mer_createdon") or ""
        created = created.replace("T", " ").split(".")[0].rstrip("Z")
        age = datetime.now(timezone.utc) - _parse_dt(created)
        status = v.get("mer_status") or "open"
        return {
            "id": int(v.get("mer_caseid") or 0),
            "applicant_name": v.get("mer_applicantname") or "",
            "dob": v.get("mer_dob") or "",
            "email": v.get("mer_email") or "",
            "phone": v.get("mer_phone") or "",
            "address": v.get("mer_address") or "",
            "national_id": v.get("mer_nationalid") or "",
            "country": v.get("mer_country") or "",
            "status": status,
            "risk_score": int(v.get("mer_riskscore") or 0),
            "risk_level": risk_level(int(v.get("mer_riskscore") or 0)),
            "assignee": v.get("mer_assignee"),
            "created_at": created,
            "decided_at": v.get("mer_decidedat"),
            "sla_breached": status == "open" and age > timedelta(hours=SLA_HOURS),
        }

    def _case_by_id(self, case_id: int) -> dict | None:
        rows = self._query(self._entity, f"mer_caseid eq {int(case_id)}")
        return rows[0] if rows else None

    def _rowid(self, case_id: int) -> str | None:
        row = self._case_by_id(case_id)
        return row.get("mer_kyccaseid") or row.get("id") if row else None

    # --- repository interface ---
    @contextmanager
    def transaction(self):
        tx = _DvTx()
        try:
            yield tx
        finally:
            tx.close()

    def list_cases(self, tx=None, *, status=None, min_risk=None, max_risk=None):
        parts = []
        if status:
            parts.append(f"mer_status eq '{status}'")
        if min_risk is not None:
            parts.append(f"mer_riskscore ge {int(min_risk)}")
        if max_risk is not None:
            parts.append(f"mer_riskscore le {int(max_risk)}")
        rows = self._query(self._entity, " and ".join(parts))
        cases = [self._to_record(r) for r in rows]
        for c in cases:
            c["approvals"] = self._approvals(c["id"])
            c["approvals_required"] = 2 if c["risk_score"] >= 70 else 1
        return cases

    def get_case(self, case_id: int, tx=None):
        row = self._case_by_id(case_id)
        if row is None:
            return None
        from app.kyc import HIGH_RISK_THRESHOLD

        c = self._to_record(row)
        c["approvals"] = self._approvals(case_id)
        c["approvals_required"] = 2 if c["risk_score"] >= HIGH_RISK_THRESHOLD else 1
        return c

    def _approvals(self, case_id: int) -> list[str]:
        rows = self._query(
            "mer_kycapprovals", f"mer_caseid eq {int(case_id)}", "mer_actor"
        )
        return [r.get("mer_actor") for r in rows if r.get("mer_actor")]

    def get_documents(self, case_id: int, tx=None):
        rows = self._query("mer_kycdocuments", f"mer_caseid eq {int(case_id)}")
        return [
            {"id": i + 1, "doc_type": r.get("mer_doctype") or "", "filename": r.get("mer_filename") or ""}
            for i, r in enumerate(rows)
        ]

    def get_hits(self, case_id: int, tx=None):
        rows = self._query("mer_kycscreeninghits", f"mer_caseid eq {int(case_id)}")
        return [
            {
                "id": i + 1,
                "hit_type": r.get("mer_hittype") or "",
                "match_name": r.get("mer_matchname") or "",
                "score": int(r.get("mer_score") or 0),
                "summary": r.get("mer_summary") or "",
            }
            for i, r in enumerate(rows)
        ]

    def get_notes(self, case_id: int, tx=None):
        rows = self._query("mer_kycnotes", f"mer_caseid eq {int(case_id)}")
        return [
            {
                "id": i + 1,
                "author": r.get("mer_author") or "",
                "body": r.get("mer_body") or "",
                "created_at": (r.get("createdon") or "").replace("T", " ").rstrip("Z"),
            }
            for i, r in enumerate(rows)
        ]

    def update_case(self, tx, case_id: int, fields: dict):
        rowid = self._rowid(case_id)
        if rowid is None:
            raise KeyError(f"case {case_id} not found")
        mapping = {
            "status": "mer_status",
            "assignee": "mer_assignee",
            "decided_at": "mer_decidedat",
        }
        body = {mapping[k]: v for k, v in fields.items() if k in mapping}
        if body:
            self._req("PATCH", self._url(self._entity, f"({rowid})"), json=body)

    def add_approval(self, tx, case_id: int, actor: str):
        self._req(
            "POST",
            self._url("mer_kycapprovals"),
            json={"mer_caseid": int(case_id), "mer_actor": actor},
        )

    def add_escalation(self, tx, case_id: int, actor: str, reason_code: str):
        self._req(
            "POST",
            self._url("mer_kycescalations"),
            json={"mer_caseid": int(case_id), "mer_actor": actor, "mer_reasoncode": reason_code},
        )

    def has_escalated(self, tx, case_id: int, actor: str) -> bool:
        rows = self._query(
            "mer_kycescalations",
            f"mer_caseid eq {int(case_id)} and mer_actor eq '{actor}'",
            "mer_kycescalationid",
        )
        return bool(rows)

    def add_note(self, tx, case_id: int, author: str, body: str) -> dict:
        res = self._req(
            "POST",
            self._url("mer_kycnotes"),
            json={"mer_caseid": int(case_id), "mer_author": author, "mer_body": body},
        )
        created = res.json() if res.content else {}
        return {
            "id": created.get("mer_kycnoteid", 0),
            "author": author,
            "body": body,
            "created_at": created.get("createdon", ""),
        }

    def write_audit(self, tx, **kw):
        _write_audit(tx.audit_conn(), **kw)
