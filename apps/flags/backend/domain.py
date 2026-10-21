"""Feature flags domain — schema, constants, seed data."""
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS feature_flags (
    id INTEGER PRIMARY KEY,
    key TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    enabled_dev INTEGER NOT NULL DEFAULT 0,
    enabled_staging INTEGER NOT NULL DEFAULT 0,
    enabled_prod INTEGER NOT NULL DEFAULT 0
);
"""

ENVIRONMENTS = ["dev", "staging", "prod"]

SEED = [
    ("new_onboarding_flow", "Reworked KYC onboarding wizard", 1, 1, 0),
    ("instant_refunds", "Auto-approve refunds below $5", 1, 0, 0),
    ("dark_mode", "Dark theme for the portal", 1, 1, 1),
    ("export_csv", "CSV export on list views", 0, 0, 0),
    ("beta_screening_v2", "Second screening vendor (shadow mode)", 1, 0, 0),
    ("rate_limit_v2", "Stricter API rate limiting", 0, 1, 0),
]


def seed_flags(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT COUNT(*) c FROM feature_flags").fetchone()["c"]:
        return
    conn.executemany(
        "INSERT INTO feature_flags (key, description, enabled_dev,"
        " enabled_staging, enabled_prod) VALUES (?,?,?,?,?)",
        SEED,
    )
    conn.commit()
