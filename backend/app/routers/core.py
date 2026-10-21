from fastapi import APIRouter, Depends

from ..auth import get_current_user, require_role
from ..db import get_db
from ..models import AuditEntryOut, ToolOut, UserOut
from ..tools import TOOLS

router = APIRouter(prefix="/api", tags=["core"])


@router.get("/tools", response_model=list[ToolOut])
def list_tools(user: dict = Depends(get_current_user)):
    """Tools the logged-in role may access."""
    return [ToolOut(**t) for t in TOOLS if user["role"] in t["roles"]]


@router.get("/users", response_model=list[UserOut])
def list_users(user: dict = Depends(require_role("admin"))):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, username, display_name, role FROM users ORDER BY id"
        ).fetchall()
    return [UserOut(**dict(r)) for r in rows]


@router.get("/audit", response_model=list[AuditEntryOut])
def list_audit(user: dict = Depends(get_current_user)):
    """Admins see the full log; reviewers only their own actions."""
    with get_db() as conn:
        if user["role"] == "admin":
            rows = conn.execute(
                "SELECT * FROM audit_log ORDER BY id DESC LIMIT 500"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM audit_log WHERE actor = ? ORDER BY id DESC LIMIT 500",
                (user["username"],),
            ).fetchall()
    return [AuditEntryOut(**dict(r)) for r in rows]
