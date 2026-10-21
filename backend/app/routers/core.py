from fastapi import APIRouter, Depends

from ..auth import get_current_user, require_permission
from portal_platform.rbac import register_permissions
from portal_platform.tools import register_tool, registered_tools

from ..db import get_db
from ..models import AuditEntryOut, DashboardSummary, ToolOut, UserOut

# directory.read stays admin-only (admin has "*").
register_permissions({"reviewer": {"audit.read"}, "read_only": {"audit.read"}})

router = APIRouter(prefix="/api", tags=["core"])


@router.get("/tools", response_model=list[ToolOut])
def list_tools(user: dict = Depends(get_current_user)):
    """Tools the logged-in role may access."""
    return [ToolOut(**t.public()) for t in registered_tools() if user["role"] in t.roles]


@router.get("/users", response_model=list[UserOut])
def list_users(user: dict = Depends(require_permission("directory.read"))):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, username, display_name, role FROM users ORDER BY id"
        ).fetchall()
    return [UserOut(**dict(r)) for r in rows]


@router.get("/audit", response_model=list[AuditEntryOut])
def list_audit(user: dict = Depends(require_permission("audit.read"))):
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


def _recent_activity(user: dict, limit: int) -> list[AuditEntryOut]:
    with get_db() as conn:
        if user["role"] == "admin":
            rows = conn.execute(
                "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM audit_log WHERE actor = ? ORDER BY id DESC LIMIT ?",
                (user["username"], limit),
            ).fetchall()
    return [AuditEntryOut(**dict(r)) for r in rows]


register_tool(
    "directory",
    name="User directory",
    description="Browse portal users and their roles.",
    path="/directory",
    roles=["admin"],
    order=40,
)
register_tool(
    "audit-trail",
    name="Audit trail",
    description="See the audit log — admins see everything, reviewers see their own actions.",
    path="/audit",
    roles=["reviewer", "admin", "read_only"],
    order=50,
    summary=lambda user: [
        {"label": "Recent events", "value": len(_recent_activity(user, 8))}
    ],
)


@router.get("/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(user: dict = Depends(get_current_user)):
    """Role-aware per-tool stats for the home dashboard. Each tool's stats
    come from the summary() it registered (apps read via their adapter)."""
    stats = {
        t.id: t.summary(user)
        for t in registered_tools()
        if t.summary and user["role"] in t.roles
    }
    return DashboardSummary(stats=stats, recent_activity=_recent_activity(user, 8))
