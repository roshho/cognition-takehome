"""SQL adapter base — a table-backed repository over the portal SQLite DB.

``transaction()`` yields the sqlite connection itself, so a mutation and
its audit row commit in the same transaction (get_db commits on exit).
Column names are checked against ``columns`` before being placed in SQL;
values are always parameterized.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from ..audit import write_audit as _write_audit


class SqlRepository:
    table: str = ""
    key: str = "id"
    columns: frozenset[str] = frozenset()  # filterable/updatable, besides key
    order_by: str = "id"

    def transaction(self):
        # Lazy import: portal_platform must not import `app` at load time.
        from app.db import get_db

        return get_db()

    @contextmanager
    def _conn(self, tx):
        if tx is not None:
            yield tx
        else:
            with self.transaction() as conn:
                yield conn

    def _check(self, names) -> None:
        bad = set(names) - self.columns - {self.key}
        if bad:
            raise ValueError(f"unknown column(s) for {self.table}: {sorted(bad)}")

    def _row(self, conn, row) -> dict:
        """Hook for subclasses to shape a row (derived fields etc.)."""
        return dict(row)

    def _select(self, tx, clauses: list[str], params: list, order_by: str | None = None) -> list[dict]:
        q = f"SELECT * FROM {self.table}"
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += f" ORDER BY {order_by or self.order_by}"
        with self._conn(tx) as conn:
            return [self._row(conn, r) for r in conn.execute(q, params).fetchall()]

    def list(self, tx=None, **equals) -> list[dict]:
        equals = {k: v for k, v in equals.items() if v is not None}
        self._check(equals)
        return self._select(tx, [f"{c} = ?" for c in equals], list(equals.values()))

    def get(self, key: Any, tx=None) -> dict | None:
        with self._conn(tx) as conn:
            row = conn.execute(
                f"SELECT * FROM {self.table} WHERE {self.key} = ?", (key,)
            ).fetchone()
            return self._row(conn, row) if row else None

    def update(self, tx, key: Any, fields: dict) -> None:
        self._check(fields)
        sets = ", ".join(f"{c} = ?" for c in fields)
        tx.execute(
            f"UPDATE {self.table} SET {sets} WHERE {self.key} = ?", (*fields.values(), key)
        )

    def insert(self, tx, fields: dict) -> dict:
        self._check(fields)
        cols = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        cur = tx.execute(f"INSERT INTO {self.table} ({cols}) VALUES ({marks})", tuple(fields.values()))
        key = fields.get(self.key, cur.lastrowid)
        return self.get(key, tx)

    def write_audit(self, tx, **kw) -> None:
        _write_audit(tx, **kw)

    def audit_history(self, entity: str, entity_id: Any, tx=None) -> list[dict]:
        """Audit rows for one record, newest first (read-only)."""
        with self._conn(tx) as conn:
            rows = conn.execute(
                "SELECT id, actor, action, before, after, created_at FROM audit_log"
                " WHERE entity = ? AND entity_id = ? ORDER BY id DESC",
                (entity, str(entity_id)),
            ).fetchall()
            return [dict(r) for r in rows]
