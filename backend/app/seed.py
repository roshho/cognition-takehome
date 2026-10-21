import sqlite3

USERS = [
    ("rana", "Rana Alvarez", "reviewer"),
    ("kwon", "Min-Jae Kwon", "reviewer"),
    ("priya", "Priya Natarajan", "admin"),
    ("marco", "Marco Reyes", "read_only"),
]


def seed(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO users (username, display_name, role) VALUES (?, ?, ?)",
        USERS,
    )
    conn.commit()
