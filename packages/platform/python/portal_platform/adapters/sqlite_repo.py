"""SQL adapter — the real repository over the app's SQLite database.

``transaction()`` yields the sqlite connection itself, so the mutation and
its audit row commit in the same transaction (get_db commits on exit).
"""
from ..audit import write_audit as _write_audit


class SqlKycRepository:
    def transaction(self):
        # Imported lazily — portal_platform must not import `app` at module
        # load time (the app imports portal_platform first).
        from app.db import get_db

        return get_db()

    def _conn(self, tx):
        if tx is not None:
            return _Ctx(tx)
        from app.db import get_db

        return get_db()

    def list_cases(self, tx=None, *, status=None, min_risk=None, max_risk=None):
        from app.kyc import case_row

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
        from app.kyc import case_row

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
        cols, params = [], []
        for k, v in fields.items():
            cols.append(f"{k} = ?")
            params.append(v)
        tx.execute(f"UPDATE kyc_cases SET {', '.join(cols)} WHERE id = ?", (*params, case_id))

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

    def write_audit(self, tx, **kw):
        _write_audit(tx, **kw)


class _Ctx:
    """Wrap an existing connection in the same context-manager shape as
    get_db() but without committing or closing it — the caller owns it."""

    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, *a):
        return False
