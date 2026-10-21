from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..audit import write_audit
from ..auth import require_role
from ..db import get_db
from ..flags import ENVIRONMENTS

router = APIRouter(prefix="/api/flags", tags=["flags"])

flags_user = require_role("reviewer", "admin")


class FlagOut(BaseModel):
    id: int
    key: str
    description: str
    enabled_dev: bool
    enabled_staging: bool
    enabled_prod: bool


class ToggleRequest(BaseModel):
    environment: str


class FlagHistoryEntry(BaseModel):
    id: int
    actor: str
    action: str
    before: str | None
    after: str | None
    created_at: str


def flag_row(row) -> dict:
    r = dict(row)
    for env in ENVIRONMENTS:
        r[f"enabled_{env}"] = bool(r[f"enabled_{env}"])
    return r


@router.get("", response_model=list[FlagOut])
def list_flags(user: dict = Depends(flags_user)):
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM feature_flags ORDER BY key").fetchall()
    return [flag_row(r) for r in rows]


@router.post("/{key}/toggle", response_model=FlagOut)
def toggle(key: str, body: ToggleRequest, user: dict = Depends(flags_user)):
    env = body.environment
    if env not in ENVIRONMENTS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"environment must be one of: {', '.join(ENVIRONMENTS)}",
        )
    # prod toggles are admin-only; dev/staging are open to both roles.
    if env == "prod" and user["role"] != "admin":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Toggling production flags requires an admin",
        )
    col = f"enabled_{env}"
    with get_db() as conn:
        row = conn.execute("SELECT * FROM feature_flags WHERE key = ?", (key,)).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Flag not found")
        flag = dict(row)
        new_val = 0 if flag[col] else 1
        conn.execute(f"UPDATE feature_flags SET {col} = ? WHERE key = ?", (new_val, key))
        write_audit(
            conn,
            actor=user["username"],
            action="flag.toggle",
            entity="feature_flag",
            entity_id=key,
            before={env: bool(flag[col])},
            after={env: bool(new_val)},
        )
        updated = conn.execute(
            "SELECT * FROM feature_flags WHERE key = ?", (key,)
        ).fetchone()
    return flag_row(updated)


@router.get("/{key}/history", response_model=list[FlagHistoryEntry])
def history(key: str, user: dict = Depends(flags_user)):
    """Change history for a flag — straight from the shared audit log."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, actor, action, before, after, created_at FROM audit_log"
            " WHERE entity = 'feature_flag' AND entity_id = ? ORDER BY id DESC",
            (key,),
        ).fetchall()
    return [FlagHistoryEntry(**dict(r)) for r in rows]
