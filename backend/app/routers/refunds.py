from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..audit import write_audit
from ..auth import require_role
from ..db import get_db
from ..refunds import ADMIN_THRESHOLD_CENTS

router = APIRouter(prefix="/api/refunds", tags=["refunds"])

refunds_user = require_role("reviewer", "admin")


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


def refund_row(row) -> dict:
    r = dict(row)
    r["requires_admin"] = r["amount_cents"] >= ADMIN_THRESHOLD_CENTS
    return r


@router.get("", response_model=list[RefundOut])
def list_refunds(
    status: str | None = None,
    min_amount: int | None = None,
    max_amount: int | None = None,
    user: dict = Depends(refunds_user),
):
    q = "SELECT * FROM refunds WHERE 1=1"
    params: list = []
    if status:
        q += " AND status = ?"
        params.append(status)
    if min_amount is not None:
        q += " AND amount_cents >= ?"
        params.append(min_amount)
    if max_amount is not None:
        q += " AND amount_cents <= ?"
        params.append(max_amount)
    q += " ORDER BY created_at DESC"
    with get_db() as conn:
        rows = conn.execute(q, params).fetchall()
    return [refund_row(r) for r in rows]


@router.get("/stats", response_model=RefundStats)
def stats(user: dict = Depends(refunds_user)):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) c, COALESCE(SUM(amount_cents), 0) amt"
            " FROM refunds GROUP BY status"
        ).fetchall()
    by = {r["status"]: (r["c"], r["amt"]) for r in rows}
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


def _decide(refund_id: int, verb: str, new_status: str, body: DecideRequest, user: dict):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM refunds WHERE id = ?", (refund_id,)).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Refund not found")
        refund = dict(row)
        if refund["status"] != "pending":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Refund is already {refund['status']}",
            )
        if refund["amount_cents"] >= ADMIN_THRESHOLD_CENTS and user["role"] != "admin":
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Refunds over ${ADMIN_THRESHOLD_CENTS / 100:,.0f} require an admin",
            )
        conn.execute(
            "UPDATE refunds SET status = ?, decided_by = ?, decided_at = datetime('now')"
            " WHERE id = ?",
            (new_status, user["username"], refund_id),
        )
        write_audit(
            conn,
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
            user: dict = Depends(refunds_user)):
    return _decide(refund_id, "approve", "approved", body or DecideRequest(), user)


@router.post("/{refund_id}/deny")
def deny(refund_id: int, body: DecideRequest | None = None,
         user: dict = Depends(refunds_user)):
    return _decide(refund_id, "deny", "denied", body or DecideRequest(), user)
