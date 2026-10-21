"""__APP_TITLE__ — generated internal app (see AGENTS.md for conventions).

Every endpoint uses require_permission(...): UI hiding is cosmetic, the
backend enforces. Every mutation writes an audit row in the same DB
transaction. Input is validated with pydantic. The app's table is registered
with the platform schema registry, so init_db() creates it like the
built-in tools' tables.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth import require_permission
from app.db import get_db
from portal_platform.audit import write_audit
from portal_platform.db import register_schema
from portal_platform.rbac import register_permissions

APP = "__APP__"
TABLE = "__APP_TABLE__"

register_schema(
    APP,
    f"""
    CREATE TABLE IF NOT EXISTS {TABLE} (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed')),
        owner TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT
    );
    """,
)

# Role grants for this app (admin already has "*"). register_permissions
# unions these into the platform's ROLE_PERMISSIONS at import time.
register_permissions({
    "reviewer": {f"{APP}.read", f"{APP}.write"},
    "read_only": {f"{APP}.read"},
})

router = APIRouter(prefix=f"/api/{APP}", tags=[APP])


class ItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ItemOut(BaseModel):
    id: int
    name: str
    status: str
    owner: str | None
    created_at: str
    updated_at: str | None


def _row(conn, item_id: int):
    return conn.execute(f"SELECT * FROM {TABLE} WHERE id = ?", (item_id,)).fetchone()


@router.get("/items", response_model=list[ItemOut])
def list_items(user: dict = Depends(require_permission(f"{APP}.read"))):
    with get_db() as conn:
        rows = conn.execute(f"SELECT * FROM {TABLE} ORDER BY id").fetchall()
    return [dict(r) for r in rows]


@router.post("/items", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
def create_item(body: ItemIn, user: dict = Depends(require_permission(f"{APP}.write"))):
    with get_db() as conn:
        cur = conn.execute(f"INSERT INTO {TABLE} (name, owner) VALUES (?, ?)", (body.name, user["username"]))
        item = dict(_row(conn, cur.lastrowid))
        write_audit(conn, actor=user["username"], action=f"{APP}.create",
                    entity=TABLE, entity_id=item["id"], before=None, after=item)
    return item


@router.post("/items/{item_id}/close", response_model=ItemOut)
def close_item(item_id: int, user: dict = Depends(require_permission(f"{APP}.write"))):
    with get_db() as conn:
        row = _row(conn, item_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "item not found")
        before = dict(row)
        conn.execute(f"UPDATE {TABLE} SET status='closed', updated_at=datetime('now') WHERE id=?", (item_id,))
        after = dict(_row(conn, item_id))
        write_audit(conn, actor=user["username"], action=f"{APP}.close",
                    entity=TABLE, entity_id=item_id, before=before, after=after)
    return after
