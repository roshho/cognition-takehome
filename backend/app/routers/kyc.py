from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..audit import write_audit
from ..auth import require_role
from ..db import get_db
from ..kyc import (
    ESCALATE_REASON_CODES,
    REJECT_REASON_CODES,
    case_row,
    mask_pii,
    required_approvals,
)

router = APIRouter(prefix="/api/kyc", tags=["kyc"])

# Both roles may work the queue; per-action rules (four-eyes etc.) still apply.
kyc_user = require_role("reviewer", "admin")


class KycCaseListItem(BaseModel):
    id: int
    applicant_name: str
    country: str
    status: str
    risk_score: int
    risk_level: str
    assignee: str | None
    created_at: str
    sla_breached: bool
    approvals: list[str]
    approvals_required: int


class DocumentOut(BaseModel):
    id: int
    doc_type: str
    filename: str


class HitOut(BaseModel):
    id: int
    hit_type: str
    match_name: str
    score: int
    summary: str


class NoteOut(BaseModel):
    id: int
    author: str
    body: str
    created_at: str


class KycCaseDetail(KycCaseListItem):
    # applicant PII — masked
    dob: str
    email: str
    phone: str
    address: str
    national_id: str
    decided_at: str | None
    documents: list[DocumentOut]
    hits: list[HitOut]
    notes: list[NoteOut]


class PiiOut(BaseModel):
    dob: str
    email: str
    phone: str
    address: str
    national_id: str


class ReasonRequest(BaseModel):
    reason_code: str


class NoteRequest(BaseModel):
    body: str


def get_open_case(conn, case_id: int):
    row = conn.execute("SELECT * FROM kyc_cases WHERE id = ?", (case_id,)).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")
    return case_row(conn, row)


def require_open(case: dict):
    if case["status"] != "open":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Case is {case['status']} — only open cases can be actioned",
        )


@router.get("/reason-codes")
def reason_codes(user: dict = Depends(kyc_user)):
    return {"reject": REJECT_REASON_CODES, "escalate": ESCALATE_REASON_CODES}


@router.get("/cases", response_model=list[KycCaseListItem])
def list_cases(
    status: str | None = None,
    min_risk: int | None = None,
    max_risk: int | None = None,
    user: dict = Depends(kyc_user),
):
    q = "SELECT * FROM kyc_cases WHERE 1=1"
    params: list = []
    if status:
        q += " AND status = ?"
        params.append(status)
    if min_risk is not None:
        q += " AND risk_score >= ?"
        params.append(min_risk)
    if max_risk is not None:
        q += " AND risk_score <= ?"
        params.append(max_risk)
    q += " ORDER BY created_at"
    with get_db() as conn:
        rows = conn.execute(q, params).fetchall()
        cases = [case_row(conn, r) for r in rows]
    # SLA breaches first, then highest risk
    cases.sort(key=lambda c: (not c["sla_breached"], -c["risk_score"]))
    return cases


@router.get("/cases/{case_id}", response_model=KycCaseDetail)
def get_case(case_id: int, user: dict = Depends(kyc_user)):
    with get_db() as conn:
        case = get_open_case(conn, case_id)
        masked = mask_pii(case)
        docs = conn.execute(
            "SELECT id, doc_type, filename FROM kyc_documents WHERE case_id = ?",
            (case_id,),
        ).fetchall()
        hits = conn.execute(
            "SELECT id, hit_type, match_name, score, summary FROM kyc_screening_hits"
            " WHERE case_id = ?",
            (case_id,),
        ).fetchall()
        notes = conn.execute(
            "SELECT id, author, body, created_at FROM kyc_notes WHERE case_id = ?"
            " ORDER BY id",
            (case_id,),
        ).fetchall()
    masked["documents"] = [dict(d) for d in docs]
    masked["hits"] = [dict(h) for h in hits]
    masked["notes"] = [dict(n) for n in notes]
    return masked


@router.post("/cases/{case_id}/unmask", response_model=PiiOut)
def unmask_pii(case_id: int, user: dict = Depends(kyc_user)):
    """Reveal applicant PII — audited, because reading PII is a decision too."""
    with get_db() as conn:
        case = get_open_case(conn, case_id)
        write_audit(
            conn,
            actor=user["username"],
            action="kyc.unmask_pii",
            entity="kyc_case",
            entity_id=case_id,
            after={"applicant_name": case["applicant_name"]},
        )
    return PiiOut(
        dob=case["dob"],
        email=case["email"],
        phone=case["phone"],
        address=case["address"],
        national_id=case["national_id"],
    )


@router.post("/cases/{case_id}/assign")
def assign_to_me(case_id: int, user: dict = Depends(kyc_user)):
    with get_db() as conn:
        case = get_open_case(conn, case_id)
        require_open(case)
        conn.execute(
            "UPDATE kyc_cases SET assignee = ? WHERE id = ?",
            (user["username"], case_id),
        )
        write_audit(
            conn,
            actor=user["username"],
            action="kyc.assign",
            entity="kyc_case",
            entity_id=case_id,
            before={"assignee": case["assignee"]},
            after={"assignee": user["username"]},
        )
    return {"ok": True, "assignee": user["username"]}


@router.post("/cases/{case_id}/approve")
def approve(case_id: int, user: dict = Depends(kyc_user)):
    """Approve a case. High-risk cases (score >= 70) need two distinct
    approvers — the four-eyes rule. Nobody can be both pairs of eyes."""
    with get_db() as conn:
        case = get_open_case(conn, case_id)
        require_open(case)
        if user["username"] in case["approvals"]:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "You already approved this case — a second reviewer is required",
            )
        try:
            conn.execute(
                "INSERT INTO kyc_approvals (case_id, actor) VALUES (?, ?)",
                (case_id, user["username"]),
            )
        except Exception:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "You already approved this case — a second reviewer is required",
            )
        approvals = case["approvals"] + [user["username"]]
        fully_approved = len(approvals) >= required_approvals(case["risk_score"])
        if fully_approved:
            conn.execute(
                "UPDATE kyc_cases SET status = 'approved', decided_at = datetime('now')"
                " WHERE id = ?",
                (case_id,),
            )
        write_audit(
            conn,
            actor=user["username"],
            action="kyc.approve",
            entity="kyc_case",
            entity_id=case_id,
            before={"status": case["status"], "approvals": case["approvals"]},
            after={
                "status": "approved" if fully_approved else case["status"],
                "approvals": approvals,
            },
        )
    return {
        "ok": True,
        "approvals": approvals,
        "approvals_required": required_approvals(case["risk_score"]),
        "status": "approved" if fully_approved else "open",
        "awaiting_second_reviewer": not fully_approved,
    }


def _decide(case_id: int, verb: str, new_status: str, body: ReasonRequest,
            allowed: list[str], user: dict):
    if body.reason_code not in allowed:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"reason_code must be one of: {', '.join(allowed)}",
        )
    with get_db() as conn:
        case = get_open_case(conn, case_id)
        require_open(case)
        conn.execute(
            "UPDATE kyc_cases SET status = ?, decided_at = datetime('now') WHERE id = ?",
            (new_status, case_id),
        )
        write_audit(
            conn,
            actor=user["username"],
            action=f"kyc.{verb}",
            entity="kyc_case",
            entity_id=case_id,
            before={"status": case["status"]},
            after={"status": new_status, "reason_code": body.reason_code},
        )
    return {"ok": True, "status": new_status, "reason_code": body.reason_code}


@router.post("/cases/{case_id}/reject")
def reject(case_id: int, body: ReasonRequest, user: dict = Depends(kyc_user)):
    return _decide(case_id, "reject", "rejected", body, REJECT_REASON_CODES, user)


@router.post("/cases/{case_id}/escalate")
def escalate(case_id: int, body: ReasonRequest, user: dict = Depends(kyc_user)):
    return _decide(case_id, "escalate", "escalated", body, ESCALATE_REASON_CODES, user)


@router.post("/cases/{case_id}/notes", response_model=NoteOut)
def add_note(case_id: int, body: NoteRequest, user: dict = Depends(kyc_user)):
    text = body.body.strip()
    if not text:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Note body is empty")
    with get_db() as conn:
        get_open_case(conn, case_id)
        cur = conn.execute(
            "INSERT INTO kyc_notes (case_id, author, body) VALUES (?, ?, ?)",
            (case_id, user["username"], text),
        )
        write_audit(
            conn,
            actor=user["username"],
            action="kyc.add_note",
            entity="kyc_case",
            entity_id=case_id,
            after={"note": text},
        )
        row = conn.execute(
            "SELECT id, author, body, created_at FROM kyc_notes WHERE id = ?",
            (cur.lastrowid,),
        ).fetchone()
    return NoteOut(**dict(row))
