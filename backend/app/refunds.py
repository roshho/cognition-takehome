"""Refunds domain — schema, constants, seed data."""
import sqlite3
from datetime import datetime, timedelta, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS refunds (
    id INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL,
    customer_email TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD',
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'denied')),
    created_at TEXT NOT NULL,
    decided_by TEXT,
    decided_at TEXT
);
"""

# Refunds at or above this amount can only be decided by an admin.
ADMIN_THRESHOLD_CENTS = 1_000_000  # $10,000.00

NAMES = [
    "Amara Okafor", "Jonas Bergstrom", "Mei Tanaka", "Tunde Adeyemi",
    "Ines Moreau", "Viktor Petrov", "Sana Rahman", "Diego Vargas",
    "Freya Larsen", "Omar Haddad", "Lucia Silva", "Kenji Sato",
    "Nadia Kovacs", "Pieter van Dijk", "Zoya Sorokina", "Marco Rossi",
]
REASONS = [
    "duplicate_charge", "item_not_received", "fraud_claim",
    "service_not_rendered", "customer_request",
]


def _dt(days_ago: int, hours_ago: int = 0) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=hours_ago)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def seed_refunds(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT COUNT(*) c FROM refunds").fetchone()["c"]:
        return
    # (status, amount_cents, days_old)
    plan = [
        ("pending", 2_500_00, 0), ("pending", 480_00, 1), ("pending", 15_400_00, 1),
        ("pending", 1_250_00, 2), ("pending", 99_00, 0), ("pending", 7_800_00, 3),
        ("pending", 25_000_00, 1), ("pending", 640_00, 4), ("pending", 12_000_00, 0),
        ("approved", 3_200_00, 9), ("approved", 18_500_00, 12), ("approved", 210_00, 7),
        ("denied", 950_00, 8), ("denied", 44_000_00, 14), ("denied", 300_00, 10),
        ("pending", 5_600_00, 2),
    ]
    for i, (status, amount, days) in enumerate(plan):
        name = NAMES[i]
        email = name.lower().replace(" ", ".") + "@example.com"
        decided_by = decided_at = None
        if status != "pending":
            decided_by = "priya" if amount >= ADMIN_THRESHOLD_CENTS else "rana"
            decided_at = _dt(max(days - 1, 0))
        conn.execute(
            "INSERT INTO refunds (customer_name, customer_email, amount_cents,"
            " reason, status, created_at, decided_by, decided_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (name, email, amount, REASONS[i % len(REASONS)], status,
             _dt(days), decided_by, decided_at),
        )
    conn.commit()
