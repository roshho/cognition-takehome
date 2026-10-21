"""SQLite connect + schema registry shared by every portal app.

Apps register their DDL via ``register_schema(name, ddl)`` (and seed data
via ``register_seed``) at import time; ``init_db`` applies all registered
DDL and ``run_seeds`` runs the seeds. ``connect`` installs the audit
append-only authorizer so the guarantee holds no matter which app's
connection issued the statement.
"""
import sqlite3
from pathlib import Path
from typing import Callable

from .audit import audit_append_only_guard

_SCHEMAS: dict[str, str] = {}
_SEEDS: dict[str, Callable[[sqlite3.Connection], None]] = {}


def register_schema(name: str, ddl: str) -> None:
    """Register an app's DDL so init_db creates its tables. Idempotent —
    re-registration with the same name replaces the DDL."""
    _SCHEMAS[name] = ddl


def register_seed(name: str, fn: Callable[[sqlite3.Connection], None]) -> None:
    """Register an app's idempotent seed function (run on startup)."""
    _SEEDS[name] = fn


def run_seeds(conn: sqlite3.Connection) -> None:
    for fn in _SEEDS.values():
        fn(conn)


def registered_schemas() -> dict[str, str]:
    return dict(_SCHEMAS)


def connect(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # Append-only enforcement for the audit log: SQLite has no per-role
    # GRANT, so the connection authorizer denies UPDATE/DELETE on the table.
    # (Production Postgres equivalent: REVOKE UPDATE, DELETE.)
    conn.set_authorizer(audit_append_only_guard)
    return conn


def init_db(path: Path | str, migrate: Callable[[sqlite3.Connection], None] | None = None) -> None:
    conn = connect(path)
    try:
        for ddl in _SCHEMAS.values():
            conn.executescript(ddl)
        if migrate:
            migrate(conn)
        conn.commit()
    finally:
        conn.close()
