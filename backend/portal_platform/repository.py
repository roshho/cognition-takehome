"""Case repository interface — the KYC app talks to this, never to the DB.

Core trio is ``list_cases`` / ``get_case`` / ``update_case``; the rest are
the case aggregate's sub-resources (documents, hits, notes, approvals,
escalations) plus ``write_audit`` so each adapter controls where the audit
row lands. ``transaction()`` scopes mutations: the SQL adapter returns a
live sqlite connection (so change + audit commit together); the Dataverse
adapter returns a shim — Dataverse has no ambient transaction (see README
known gaps).
"""
from contextlib import contextmanager
from typing import Any, Protocol


class KycRepository(Protocol):
    @contextmanager
    def transaction(self):
        """Yield a tx handle for one atomic unit of work."""
        yield None

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
