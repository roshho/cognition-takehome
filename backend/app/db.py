import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from . import kyc

DB_PATH = Path(os.environ.get("PORTAL_DB_PATH", Path(__file__).resolve().parent.parent / "portal.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('reviewer', 'admin'))
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
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_db():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(path: Path | str = DB_PATH) -> None:
    conn = connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.executescript(kyc.SCHEMA)
        conn.commit()
    finally:
        conn.close()
