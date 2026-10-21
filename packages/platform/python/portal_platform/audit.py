"""Append-only audit log.

Every mutating endpoint writes through ``write_audit`` on the same
transaction as the change. A request id is attached automatically from a
contextvar set by ``RequestIdMiddleware``. On SQLite the append-only
guarantee is enforced by ``audit_append_only_guard`` — a connection
authorizer that denies UPDATE/DELETE on audit_log (SQLite has no role
grants; on Postgres the same guarantee is ``REVOKE UPDATE, DELETE``).
"""
import json
import sqlite3
import uuid
from contextvars import ContextVar
from typing import Any

_request_id: ContextVar[str | None] = ContextVar("portal_request_id", default=None)


def set_request_id(rid: str | None) -> None:
    _request_id.set(rid)


def current_request_id() -> str | None:
    return _request_id.get()


class RequestIdMiddleware:
    """ASGI middleware: one request id per HTTP request, exposed to
    write_audit via contextvar and echoed on the response."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        rid = uuid.uuid4().hex[:16]
        _request_id.set(rid)

        async def send_with_rid(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append(
                    (b"x-request-id", rid.encode())
                )
            await send(message)

        try:
            await self.app(scope, receive, send_with_rid)
        finally:
            _request_id.set(None)


def audit_append_only_guard(action, p1, p2, db_name, source):
    """sqlite3 connection authorizer: deny UPDATE/DELETE on audit_log."""
    if p1 == "audit_log" and action in (sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE):
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def write_audit(
    conn: sqlite3.Connection,
    *,
    actor: str,
    action: str,
    entity: str,
    entity_id: str | int | None = None,
    before: Any = None,
    after: Any = None,
    request_id: str | None = None,
) -> int:
    """Append a row to the append-only audit log.

    Call this on the same connection as the mutation so the audit entry
    commits atomically with the change. The request id comes from the
    middleware contextvar unless passed explicitly.
    """
    rid = request_id if request_id is not None else current_request_id()
    cur = conn.execute(
        "INSERT INTO audit_log (actor, action, entity, entity_id, before, after, request_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            actor,
            action,
            entity,
            str(entity_id) if entity_id is not None else None,
            json.dumps(before) if before is not None else None,
            json.dumps(after) if after is not None else None,
            rid,
        ),
    )
    return int(cur.lastrowid)
