from fastapi import APIRouter, Depends

from ..auth import get_current_user, require_permission
from ..db import get_db
from ..flags import ENVIRONMENTS
from ..kyc import HIGH_RISK_THRESHOLD, SLA_HOURS
from ..models import (
    AuditEntryOut,
    DashboardSummary,
    FlagsDashboard,
    KycDashboard,
    RefundsDashboard,
    ToolOut,
    UserOut,
)
from ..refunds import ADMIN_THRESHOLD_CENTS
from ..tools import TOOLS

router = APIRouter(prefix="/api", tags=["core"])


@router.get("/tools", response_model=list[ToolOut])
def list_tools(user: dict = Depends(get_current_user)):
    """Tools the logged-in role may access."""
    return [ToolOut(**t) for t in TOOLS if user["role"] in t["roles"]]


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


def _can_access(user: dict, tool_id: str) -> bool:
    tool = next((t for t in TOOLS if t["id"] == tool_id), None)
    return tool is not None and user["role"] in tool["roles"]


@router.get("/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(user: dict = Depends(get_current_user)):
    """Role-aware per-tool stats for the home dashboard."""
    summary = DashboardSummary(recent_activity=[])
    with get_db() as conn:
        if _can_access(user, "kyc-queue"):
            sla_cutoff = f"datetime('now', '-{SLA_HOURS} hours')"
            row = conn.execute(
                f"""
                SELECT
                    COUNT(*) AS open_cases,
                    SUM(CASE WHEN created_at < {sla_cutoff} THEN 1 ELSE 0 END) AS sla_breached,
                    SUM(CASE WHEN risk_score >= ? THEN 1 ELSE 0 END) AS high_risk_open,
                    SUM(CASE WHEN assignee = ? THEN 1 ELSE 0 END) AS assigned_to_me
                FROM kyc_cases WHERE status = 'open'
                """,
                (HIGH_RISK_THRESHOLD, user["username"]),
            ).fetchone()
            summary.kyc = KycDashboard(
                open_cases=row["open_cases"],
                sla_breached=row["sla_breached"] or 0,
                high_risk_open=row["high_risk_open"] or 0,
                assigned_to_me=row["assigned_to_me"] or 0,
            )
        if _can_access(user, "refunds"):
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS pending_count,
                    COALESCE(SUM(amount_cents), 0) AS pending_amount_cents,
                    SUM(CASE WHEN amount_cents >= ? THEN 1 ELSE 0 END) AS over_threshold_pending
                FROM refunds WHERE status = 'pending'
                """,
                (ADMIN_THRESHOLD_CENTS,),
            ).fetchone()
            summary.refunds = RefundsDashboard(
                pending_count=row["pending_count"],
                pending_amount_cents=row["pending_amount_cents"],
                over_threshold_pending=row["over_threshold_pending"] or 0,
            )
        if _can_access(user, "feature-flags"):
            env_counts = {
                env: conn.execute(
                    f"SELECT COUNT(*) c FROM feature_flags WHERE enabled_{env} = 1"
                ).fetchone()["c"]
                for env in ENVIRONMENTS
            }
            summary.flags = FlagsDashboard(
                total=conn.execute("SELECT COUNT(*) c FROM feature_flags").fetchone()["c"],
                enabled=env_counts,
            )
        if user["role"] == "admin":
            rows = conn.execute(
                "SELECT * FROM audit_log ORDER BY id DESC LIMIT 8"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM audit_log WHERE actor = ? ORDER BY id DESC LIMIT 8",
                (user["username"],),
            ).fetchall()
        summary.recent_activity = [AuditEntryOut(**dict(r)) for r in rows]
    return summary
