import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from portal_platform.audit import audit_append_only_guard

from . import flags, kyc, refunds

DB_PATH = Path(os.environ.get("PORTAL_DB_PATH", Path(__file__).resolve().parent.parent / "portal.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('reviewer', 'admin', 'read_only'))
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    entity TEXT NOT NULL,
    entity_id TEXT,
    before TEXT,
    after TEXT,
    request_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # Append-only enforcement for the audit log: SQLite has no per-role
    # GRANT, so the connection authorizer denies UPDATE/DELETE on the table.
    # (Production Postgres equivalent: REVOKE UPDATE, DELETE.)
    conn.set_authorizer(audit_append_only_guard)
    return conn


@contextmanager
def get_db():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """In-place upgrades for databases created by earlier builds."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(audit_log)")}
    if "request_id" not in cols:
        conn.execute("ALTER TABLE audit_log ADD COLUMN request_id TEXT")
    # SQLite can't ALTER a CHECK constraint — rebuild users if it still
    # rejects the read_only role.
    sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()["sql"]
    if "read_only" not in sql:
        conn.execute("ALTER TABLE users RENAME TO users_old")
        conn.execute(
            """CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('reviewer', 'admin', 'read_only'))
            )"""
        )
        conn.execute(
            "INSERT OR IGNORE INTO users (id, username, display_name, role) "
            "SELECT id, username, display_name, role FROM users_old"
        )
        conn.execute("DROP TABLE users_old")


def init_db(path: Path | str = DB_PATH) -> None:
    conn = connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.executescript(kyc.SCHEMA)
        conn.executescript(refunds.SCHEMA)
        conn.executescript(flags.SCHEMA)
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()
