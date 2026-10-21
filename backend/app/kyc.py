"""KYC review queue — schema, seed data, and helpers.

PII rule: GET endpoints return masked applicant data always. Revealing PII is
a separate audited action (POST .../unmask).
"""
import sqlite3
from datetime import datetime, timedelta, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS kyc_cases (
    id INTEGER PRIMARY KEY,
    applicant_name TEXT NOT NULL,
    dob TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT NOT NULL,
    address TEXT NOT NULL,
    national_id TEXT NOT NULL,
    country TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'approved', 'rejected', 'escalated')),
    risk_score INTEGER NOT NULL CHECK (risk_score BETWEEN 0 AND 100),
    assignee TEXT,
    created_at TEXT NOT NULL,
    decided_at TEXT
);
CREATE TABLE IF NOT EXISTS kyc_documents (
    id INTEGER PRIMARY KEY,
    case_id INTEGER NOT NULL REFERENCES kyc_cases(id),
    doc_type TEXT NOT NULL,
    filename TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS kyc_screening_hits (
    id INTEGER PRIMARY KEY,
    case_id INTEGER NOT NULL REFERENCES kyc_cases(id),
    hit_type TEXT NOT NULL CHECK (hit_type IN ('sanctions', 'pep')),
    match_name TEXT NOT NULL,
    score INTEGER NOT NULL,
    summary TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS kyc_notes (
    id INTEGER PRIMARY KEY,
    case_id INTEGER NOT NULL REFERENCES kyc_cases(id),
    author TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS kyc_approvals (
    id INTEGER PRIMARY KEY,
    case_id INTEGER NOT NULL REFERENCES kyc_cases(id),
    actor TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (case_id, actor)
);
CREATE TABLE IF NOT EXISTS kyc_escalations (
    id INTEGER PRIMARY KEY,
    case_id INTEGER NOT NULL REFERENCES kyc_cases(id),
    actor TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

HIGH_RISK_THRESHOLD = 70
SLA_HOURS = 48

REJECT_REASON_CODES = [
    "document_mismatch",
    "suspected_fraud",
    "failed_screening",
    "incomplete_information",
    "other",
]
ESCALATE_REASON_CODES = [
    "sanctions_hit",
    "pep_hit",
    "high_risk_score",
    "document_unclear",
    "other",
]


def risk_level(score: int) -> str:
    if score >= HIGH_RISK_THRESHOLD:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def required_approvals(risk_score: int) -> int:
    return 2 if risk_score >= HIGH_RISK_THRESHOLD else 1


def mask(value: str, keep: int = 1) -> str:
    if len(value) <= keep:
        return "•" * len(value)
    return value[:keep] + "•" * (len(value) - keep)


def mask_pii(case: dict) -> dict:
    """Applicant fields minus PII. applicant_name stays visible for triage."""
    masked = dict(case)
    masked["dob"] = "••/••/••••"
    masked["email"] = mask(case["email"].split("@")[0]) + "@•••••"
    masked["phone"] = "••••••" + case["phone"][-2:]
    masked["address"] = "••••••••••"
    masked["national_id"] = "••••••" + case["national_id"][-2:]
    return masked


def parse_dt(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def case_row(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    case = dict(row)
    case["risk_level"] = risk_level(case["risk_score"])
    age = datetime.now(timezone.utc) - parse_dt(case["created_at"])
    case["sla_breached"] = case["status"] == "open" and age > timedelta(hours=SLA_HOURS)
    approvals = conn.execute(
        "SELECT actor FROM kyc_approvals WHERE case_id = ? ORDER BY id", (case["id"],)
    ).fetchall()
    case["approvals"] = [a["actor"] for a in approvals]
    case["approvals_required"] = required_approvals(case["risk_score"])
    return case


FIRST = ["Amara", "Jonas", "Mei", "Tunde", "Ines", "Viktor", "Sana", "Diego",
         "Freya", "Omar", "Lucia", "Kenji", "Nadia", "Pieter", "Zoya", "Marco",
         "Aisha", "Stefan", "Lena", "Ravi", "Camille", "Yusuf", "Hana", "Elias",
         "Noor"]
LAST = ["Okafor", "Bergstrom", "Tanaka", "Adeyemi", "Moreau", "Petrov", "Rahman",
        "Vargas", "Larsen", "Haddad", "Silva", "Sato", "Kovacs", "van Dijk",
        "Sorokina", "Rossi", "Diallo", "Weber", "Novak", "Patel", "Dubois",
        "Nazari", "Kim", "Braun", "Haddad"]
COUNTRIES = ["Nigeria", "Sweden", "Japan", "Brazil", "France", "Germany",
             "UAE", "Netherlands", "Italy", "India", "South Korea", "Austria"]
DOC_TYPES = ["passport", "proof_of_address", "selfie"]
SANCTIONS_SUMMARIES = [
    "Name similarity with consolidated sanctions list entry; DOB mismatch.",
    "Partial name match on OFAC SDN list; nationality differs.",
]
PEP_SUMMARIES = [
    "Former regional government official (term ended 2019).",
    "Spouse of sitting municipal council member.",
]


def _dt(days_ago: int, hours_ago: int = 0) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=hours_ago)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def seed_kyc(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT COUNT(*) c FROM kyc_cases").fetchone()["c"]:
        return
    # (status, risk, days_old, hours_extra) — mix includes several SLA breaches
    plan = [
        ("open", 12, 0, 5), ("open", 24, 1, 2), ("open", 35, 2, 3),
        ("open", 48, 3, 0), ("open", 55, 4, 1), ("open", 62, 0, 49),
        ("open", 71, 2, 10), ("open", 78, 1, 30), ("open", 83, 5, 0),
        ("open", 90, 0, 60), ("open", 45, 1, 10), ("open", 30, 0, 20),
        ("open", 95, 3, 4), ("open", 52, 2, 20), ("open", 18, 1, 6),
        ("open", 67, 4, 2), ("open", 74, 0, 51), ("open", 40, 6, 0),
        ("approved", 15, 8, 0), ("approved", 38, 10, 0), ("rejected", 66, 9, 0),
        ("rejected", 20, 12, 0), ("escalated", 88, 7, 0), ("escalated", 79, 11, 0),
        ("open", 58, 2, 7),
    ]
    for i, (status, risk, days, hours) in enumerate(plan):
        first, last = FIRST[i], LAST[i]
        name = f"{first} {last}"
        country = COUNTRIES[i % len(COUNTRIES)]
        created = _dt(days, hours)
        assignee = None
        decided = None
        if status != "open":
            assignee = "rana" if i % 2 == 0 else "kwon"
            decided = _dt(max(days - 1, 0))
        elif i % 3 == 0:
            assignee = "rana" if i % 2 == 0 else "kwon"
        cur = conn.execute(
            "INSERT INTO kyc_cases (applicant_name, dob, email, phone, address,"
            " national_id, country, status, risk_score, assignee, created_at,"
            " decided_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                name,
                f"19{60 + i % 40}-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}",
                f"{first.lower()}.{last.lower().replace(' ', '')}@example.com",
                f"+{40 + i} 555 01{i:02d}",
                f"{10 + i} {last} Street, {country}",
                f"ID{country[:2].upper()}{100000 + i * 7}",
                country,
                status,
                risk,
                assignee,
                created,
                decided,
            ),
        )
        case_id = cur.lastrowid
        for doc in DOC_TYPES[: 1 + i % 3]:
            conn.execute(
                "INSERT INTO kyc_documents (case_id, doc_type, filename) VALUES (?,?,?)",
                (case_id, doc, f"{doc}_{case_id:03d}.pdf"),
            )
        if risk >= 80 or (status == "escalated" and risk >= 70):
            conn.execute(
                "INSERT INTO kyc_screening_hits (case_id, hit_type, match_name, score, summary)"
                " VALUES (?,?,?,?,?)",
                (case_id, "sanctions", name, min(99, risk + 4), SANCTIONS_SUMMARIES[i % 2]),
            )
        if 60 <= risk < 80 and i % 2 == 0:
            conn.execute(
                "INSERT INTO kyc_screening_hits (case_id, hit_type, match_name, score, summary)"
                " VALUES (?,?,?,?,?)",
                (case_id, "pep", name, risk, PEP_SUMMARIES[i % 2]),
            )
        if status in ("rejected", "escalated"):
            conn.execute(
                "INSERT INTO kyc_notes (case_id, author, body, created_at) VALUES (?,?,?,?)",
                (case_id, assignee, f"Case {status} — see decision reason.", decided),
            )
    conn.commit()
