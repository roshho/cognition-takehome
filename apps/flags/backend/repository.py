"""Feature-flag repository — the flags router talks to this, never to the DB.
Flags are keyed by ``key``; history comes from the shared audit log."""
from __future__ import annotations

from typing import Protocol

from portal_platform.adapters.sql import SqlRepository

from .domain import ENVIRONMENTS


class FlagsRepository(Protocol):
    def transaction(self): ...
    def list(self, tx=None) -> list[dict]: ...
    def get(self, key: str, tx=None) -> dict | None: ...
    def update(self, tx, key: str, fields: dict) -> None: ...
    def write_audit(self, tx, **kw) -> None: ...
    def audit_history(self, entity: str, entity_id: str, tx=None) -> list[dict]: ...


class SqlFlagsRepository(SqlRepository):
    table = "feature_flags"
    key = "key"
    columns = frozenset({"description"} | {f"enabled_{e}" for e in ENVIRONMENTS})
    order_by = "key"

    def _row(self, conn, row) -> dict:
        r = dict(row)
        for env in ENVIRONMENTS:
            r[f"enabled_{env}"] = bool(r[f"enabled_{env}"])
        return r
