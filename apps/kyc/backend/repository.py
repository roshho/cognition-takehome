"""KYC case repository — the KYC router talks to this, never to the DB.

``KycRepository`` is the case aggregate's interface: the core trio
``list_cases`` / ``get_case`` / ``update_case`` plus sub-resources
(documents, hits, notes, approvals, escalations). Two adapters implement
it: ``SqlKycRepository`` here (real) and ``DataverseKycRepository`` in
dataverse_repo.py (OData, mocked-HTTP tests only). Both pass the same
contract tests in test_kyc.py.
"""
from __future__ import annotations

from typing import Any, Protocol

from portal_platform.adapters.sql import SqlRepository

from .domain import case_row


class KycRepository(Protocol):
    def transaction(self): ...

    def list_cases(
        self,
        tx=None,
        *,
        status: str | None = None,
        min_risk: int | None = None,
        max_risk: int | None = None,
    ) -> list[dict]: ...

    def get_case(self, case_id: int, tx=None) -> dict | None: ...
    def get_documents(self, case_id: int, tx=None) -> list[dict]: ...
    def get_hits(self, case_id: int, tx=None) -> list[dict]: ...
    def get_notes(self, case_id: int, tx=None) -> list[dict]: ...

    def update_case(self, tx, case_id: int, fields: dict) -> None: ...
    def add_approval(self, tx, case_id: int, actor: str) -> None: ...
    def add_escalation(self, tx, case_id: int, actor: str, reason_code: str) -> None: ...
    def has_escalated(self, tx, case_id: int, actor: str) -> bool: ...
    def add_note(self, tx, case_id: int, author: str, body: str) -> dict: ...

    def write_audit(
        self,
        tx,
        *,
        actor: str,
        action: str,
        entity: str,
        entity_id: Any = None,
        before: Any = None,
        after: Any = None,
    ) -> None: ...


class SqlKycRepository(SqlRepository):
    """Real adapter over the portal SQLite DB. ``transaction()`` (inherited)
    yields the connection, so change + audit commit together."""

    table = "kyc_cases"
    columns = frozenset({"status", "assignee", "decided_at", "risk_score"})
    order_by = "created_at"

    def _row(self, conn, row) -> dict:
        return case_row(conn, row)

    def list_cases(self, tx=None, *, status=None, min_risk=None, max_risk=None):
        q = "SELECT * FROM kyc_cases WHERE 1=1"
        params: list = []
        if status:
            q += " AND status = ?"
            params.append(status)
        if min_risk is not None:
            q += " AND risk_score >= ?"
            params.append(min_risk)
        if max_risk is not None:
            q += " AND risk_score <= ?"
            params.append(max_risk)
        q += " ORDER BY created_at"
        with self._conn(tx) as conn:
            rows = conn.execute(q, params).fetchall()
            return [case_row(conn, r) for r in rows]

    def get_case(self, case_id: int, tx=None):
        with self._conn(tx) as conn:
            row = conn.execute(
                "SELECT * FROM kyc_cases WHERE id = ?", (case_id,)
            ).fetchone()
            return case_row(conn, row) if row else None

    def get_documents(self, case_id: int, tx=None):
        with self._conn(tx) as conn:
            return [
                dict(r)
                for r in conn.execute(
                    "SELECT id, doc_type, filename FROM kyc_documents WHERE case_id = ?",
                    (case_id,),
                ).fetchall()
            ]

    def get_hits(self, case_id: int, tx=None):
        with self._conn(tx) as conn:
            return [
                dict(r)
                for r in conn.execute(
                    "SELECT id, hit_type, match_name, score, summary FROM kyc_screening_hits"
                    " WHERE case_id = ?",
                    (case_id,),
                ).fetchall()
            ]

    def get_notes(self, case_id: int, tx=None):
        with self._conn(tx) as conn:
            return [
                dict(r)
                for r in conn.execute(
                    "SELECT id, author, body, created_at FROM kyc_notes WHERE case_id = ?"
                    " ORDER BY id",
                    (case_id,),
                ).fetchall()
            ]

    def update_case(self, tx, case_id: int, fields: dict):
        self.update(tx, case_id, fields)

    def add_approval(self, tx, case_id: int, actor: str):
        tx.execute(
            "INSERT INTO kyc_approvals (case_id, actor) VALUES (?, ?)",
            (case_id, actor),
        )

    def add_escalation(self, tx, case_id: int, actor: str, reason_code: str):
        tx.execute(
            "INSERT INTO kyc_escalations (case_id, actor, reason_code) VALUES (?, ?, ?)",
            (case_id, actor, reason_code),
        )

    def has_escalated(self, tx, case_id: int, actor: str) -> bool:
        return (
            tx.execute(
                "SELECT 1 FROM kyc_escalations WHERE case_id = ? AND actor = ? LIMIT 1",
                (case_id, actor),
            ).fetchone()
            is not None
        )

    def add_note(self, tx, case_id: int, author: str, body: str) -> dict:
        cur = tx.execute(
            "INSERT INTO kyc_notes (case_id, author, body) VALUES (?, ?, ?)",
            (case_id, author, body),
        )
        return dict(
            tx.execute(
                "SELECT id, author, body, created_at FROM kyc_notes WHERE id = ?",
                (cur.lastrowid,),
            ).fetchone()
        )

