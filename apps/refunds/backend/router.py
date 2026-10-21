from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth import require_permission
from portal_platform.db import register_schema, register_seed
from portal_platform.rbac import has_permission, register_permissions
from portal_platform.repository import get_repository, register_adapter
from portal_platform.tools import register_tool

from .domain import ADMIN_THRESHOLD_CENTS, SCHEMA, seed_refunds
from .repository import SqlRefundsRepository

APP = "refunds"

register_schema(APP, SCHEMA)
register_seed(APP, seed_refunds)
# refunds.decide_large (>= threshold) is admin-only: never granted here.
register_permissions({
    "reviewer": {"refunds.read", "refunds.decide"},
    "read_only": {"refunds.read"},
})
register_adapter(APP, "sql", SqlRefundsRepository)


def _money(cents: int) -> str:
    return f"${cents / 100:,.0f}"


def _summary(user: dict) -> list[dict]:
    pending = get_repository(APP).list(status="pending")
    over = sum(r["requires_admin"] for r in pending)
    return [
        {"label": "Pending", "value": len(pending)},
        {"label": "Pending amount", "value": _money(sum(r["amount_cents"] for r in pending))},
        {"label": "Needs admin", "value": over, "tone": "warn" if over else None},
    ]


register_tool(
    "refunds",
    name="Refunds",
    description="Approve or deny refund requests. Large refunds need an admin.",
    path="/refunds",
    roles=["reviewer", "admin", "read_only"],
    order=20,
    summary=_summary,
)

router = APIRouter(prefix="/api/refunds", tags=["refunds"])

refunds_read = require_permission("refunds.read")
refunds_decide = require_permission("refunds.decide")


class RefundOut(BaseModel):
    id: int
    customer_name: str
    customer_email: str
    amount_cents: int
    currency: str
    reason: str
    status: str
    created_at: str
    decided_by: str | None
    decided_at: str | None
    requires_admin: bool


class RefundStats(BaseModel):
    total: int
    pending_count: int
    pending_amount_cents: int
    approved_count: int
    approved_amount_cents: int
    denied_count: int
    denied_amount_cents: int
    admin_threshold_cents: int


class DecideRequest(BaseModel):
    reason: str | None = None


@router.get("", response_model=list[RefundOut])
def list_refunds(
    status: str | None = None,
    min_amount: int | None = None,
    max_amount: int | None = None,
    user: dict = Depends(refunds_read),
):
    return get_repository(APP).list(
        status=status, min_amount=min_amount, max_amount=max_amount
    )


@router.get("/stats", response_model=RefundStats)
def stats(user: dict = Depends(refunds_read)):
    by: dict[str, tuple[int, int]] = {}
    for r in get_repository(APP).list():
        c, amt = by.get(r["status"], (0, 0))
        by[r["status"]] = (c + 1, amt + r["amount_cents"])
    total = sum(c for c, _ in by.values())
    return RefundStats(
        total=total,
        pending_count=by.get("pending", (0, 0))[0],
        pending_amount_cents=by.get("pending", (0, 0))[1],
        approved_count=by.get("approved", (0, 0))[0],
        approved_amount_cents=by.get("approved", (0, 0))[1],
        denied_count=by.get("denied", (0, 0))[0],
        denied_amount_cents=by.get("denied", (0, 0))[1],
        admin_threshold_cents=ADMIN_THRESHOLD_CENTS,
    )


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _decide(refund_id: int, verb: str, new_status: str, body: DecideRequest, user: dict):
    repo = get_repository(APP)
    with repo.transaction() as tx:
        refund = repo.get(refund_id, tx)
        if refund is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Refund not found")
        if refund["status"] != "pending":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Refund is already {refund['status']}",
            )
        if refund["amount_cents"] >= ADMIN_THRESHOLD_CENTS and not has_permission(user["role"], "refunds.decide_large"):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Refunds over ${ADMIN_THRESHOLD_CENTS / 100:,.0f} require an admin",
            )
        repo.update(tx, refund_id, {
            "status": new_status,
            "decided_by": user["username"],
            "decided_at": _now(),
        })
        repo.write_audit(
            tx,
            actor=user["username"],
            action=f"refund.{verb}",
            entity="refund",
            entity_id=refund_id,
            before={"status": refund["status"]},
            after={
                "status": new_status,
                "decided_by": user["username"],
                "reason": body.reason,
            },
        )
    return {"ok": True, "status": new_status}


@router.post("/{refund_id}/approve")
def approve(refund_id: int, body: DecideRequest | None = None,
            user: dict = Depends(refunds_decide)):
    return _decide(refund_id, "approve", "approved", body or DecideRequest(), user)


@router.post("/{refund_id}/deny")
def deny(refund_id: int, body: DecideRequest | None = None,
         user: dict = Depends(refunds_decide)):
    return _decide(refund_id, "deny", "denied", body or DecideRequest(), user)
