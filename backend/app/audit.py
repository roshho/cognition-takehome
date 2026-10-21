import json
import sqlite3
from typing import Any


def write_audit(
    conn: sqlite3.Connection,
    *,
    actor: str,
    action: str,
    entity: str,
    entity_id: str | int | None = None,
    before: Any = None,
    after: Any = None,
) -> int:
    """Append a row to the append-only audit log.

    Every mutating endpoint must call this on the same connection as the
    mutation so the audit entry commits atomically with the change.
    """
    cur = conn.execute(
        "INSERT INTO audit_log (actor, action, entity, entity_id, before, after) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            actor,
            action,
            entity,
            str(entity_id) if entity_id is not None else None,
            json.dumps(before) if before is not None else None,
            json.dumps(after) if after is not None else None,
        ),
    )
    return int(cur.lastrowid)
