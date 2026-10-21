"""Refunds repository — the refunds router talks to this, never to the DB."""
from __future__ import annotations

from typing import Protocol

from portal_platform.adapters.sql import SqlRepository

from .domain import ADMIN_THRESHOLD_CENTS


class RefundsRepository(Protocol):
    def transaction(self): ...
    def list(
        self, tx=None, *, status: str | None = None,
        min_amount: int | None = None, max_amount: int | None = None,
    ) -> list[dict]: ...
    def get(self, refund_id: int, tx=None) -> dict | None: ...
    def update(self, tx, refund_id: int, fields: dict) -> None: ...
    def write_audit(self, tx, **kw) -> None: ...


class SqlRefundsRepository(SqlRepository):
    table = "refunds"
    columns = frozenset({"status", "decided_by", "decided_at", "amount_cents"})
    order_by = "created_at DESC"

    def _row(self, conn, row) -> dict:
        r = dict(row)
        r["requires_admin"] = r["amount_cents"] >= ADMIN_THRESHOLD_CENTS
        return r

    def list(self, tx=None, *, status=None, min_amount=None, max_amount=None):
        clauses, params = [], []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if min_amount is not None:
            clauses.append("amount_cents >= ?")
            params.append(min_amount)
        if max_amount is not None:
            clauses.append("amount_cents <= ?")
            params.append(max_amount)
        return self._select(tx, clauses, params)
