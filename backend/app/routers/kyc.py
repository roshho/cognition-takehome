from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from portal_platform.adapters import get_repository

from ..auth import require_permission
from ..kyc import (
    ESCALATE_REASON_CODES,
    REJECT_REASON_CODES,
    mask_pii,
    required_approvals,
)

router = APIRouter(prefix="/api/kyc", tags=["kyc"])

# Reads need kyc.read (reviewer, admin, read_only); mutations need
# kyc.decide (reviewer, admin). Enforced server-side on every call.
kyc_read = require_permission("kyc.read")
kyc_decide = require_permission("kyc.decide")
kyc_unmask = require_permission("kyc.unmask")


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


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def require_actionable(case: dict, user: dict):
    """Open cases are actionable by anyone with kyc.decide; escalated cases
    only by admins (senior review). Decided cases are final for everyone."""
    if case["status"] == "open":
        return
    if case["status"] == "escalated" and user["role"] == "admin":
        return
    raise HTTPException(
        status.HTTP_409_CONFLICT,
        f"Case is {case['status']} — cannot be actioned by your role",
    )


def deny_if_escalated_by(repo, tx, case_id: int, user: dict):
    """Separation of duties: nobody decides a case they themselves
    escalated — a second pair of eyes must take it."""
    if repo.has_escalated(tx, case_id, user["username"]):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "You escalated this case — a different reviewer must decide it",
        )


@router.get("/reason-codes")
def reason_codes(user: dict = Depends(kyc_read)):
    return {"reject": REJECT_REASON_CODES, "escalate": ESCALATE_REASON_CODES}


@router.get("/cases", response_model=list[KycCaseListItem])
def list_cases(
    status: str | None = None,
    min_risk: int | None = None,
    max_risk: int | None = None,
    user: dict = Depends(kyc_read),
):
    repo = get_repository()
    cases = repo.list_cases(status=status, min_risk=min_risk, max_risk=max_risk)
    # SLA breaches first, then highest risk
    cases.sort(key=lambda c: (not c["sla_breached"], -c["risk_score"]))
    return cases


@router.get("/cases/{case_id}", response_model=KycCaseDetail)
def get_case(case_id: int, user: dict = Depends(kyc_read)):
    repo = get_repository()
    case = repo.get_case(case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")
    masked = mask_pii(case)
    masked["documents"] = repo.get_documents(case_id)
    masked["hits"] = repo.get_hits(case_id)
    masked["notes"] = repo.get_notes(case_id)
    return masked


@router.post("/cases/{case_id}/unmask", response_model=PiiOut)
def unmask_pii(case_id: int, user: dict = Depends(kyc_unmask)):
    """Reveal applicant PII — audited, because reading PII is a decision too."""
    repo = get_repository()
    with repo.transaction() as tx:
        case = repo.get_case(case_id, tx)
        if case is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")
        repo.write_audit(
            tx,
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
def assign_to_me(case_id: int, user: dict = Depends(kyc_decide)):
    repo = get_repository()
    with repo.transaction() as tx:
        case = repo.get_case(case_id, tx)
        if case is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")
        require_actionable(case, user)
        repo.update_case(tx, case_id, {"assignee": user["username"]})
        repo.write_audit(
            tx,
            actor=user["username"],
            action="kyc.assign",
            entity="kyc_case",
            entity_id=case_id,
            before={"assignee": case["assignee"]},
            after={"assignee": user["username"]},
        )
    return {"ok": True, "assignee": user["username"]}


@router.post("/cases/{case_id}/approve")
def approve(case_id: int, user: dict = Depends(kyc_decide)):
    """Approve a case. High-risk cases (score >= 70) need two distinct
    approvers — the four-eyes rule. Nobody can be both pairs of eyes, and
    nobody may decide a case they escalated."""
    repo = get_repository()
    with repo.transaction() as tx:
        case = repo.get_case(case_id, tx)
        if case is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")
        deny_if_escalated_by(repo, tx, case_id, user)
        require_actionable(case, user)
        if user["username"] in case["approvals"]:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "You already approved this case — a second reviewer is required",
            )
        try:
            repo.add_approval(tx, case_id, user["username"])
        except Exception:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "You already approved this case — a second reviewer is required",
            )
        approvals = case["approvals"] + [user["username"]]
        fully_approved = len(approvals) >= required_approvals(case["risk_score"])
        if fully_approved:
            repo.update_case(
                tx, case_id, {"status": "approved", "decided_at": _now()}
            )
        repo.write_audit(
            tx,
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
        "status": "approved" if fully_approved else case["status"],
        "awaiting_second_reviewer": not fully_approved,
    }


def _decide(case_id: int, verb: str, new_status: str, body: ReasonRequest,
            allowed: list[str], user: dict):
    if body.reason_code not in allowed:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"reason_code must be one of: {', '.join(allowed)}",
        )
    repo = get_repository()
    with repo.transaction() as tx:
        case = repo.get_case(case_id, tx)
        if case is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")
        deny_if_escalated_by(repo, tx, case_id, user)
        require_actionable(case, user)
        repo.update_case(tx, case_id, {"status": new_status, "decided_at": _now()})
        if verb == "escalate":
            repo.add_escalation(tx, case_id, user["username"], body.reason_code)
        repo.write_audit(
            tx,
            actor=user["username"],
            action=f"kyc.{verb}",
            entity="kyc_case",
            entity_id=case_id,
            before={"status": case["status"]},
            after={"status": new_status, "reason_code": body.reason_code},
        )
    return {"ok": True, "status": new_status, "reason_code": body.reason_code}


@router.post("/cases/{case_id}/reject")
def reject(case_id: int, body: ReasonRequest, user: dict = Depends(kyc_decide)):
    return _decide(case_id, "reject", "rejected", body, REJECT_REASON_CODES, user)


@router.post("/cases/{case_id}/escalate")
def escalate(case_id: int, body: ReasonRequest, user: dict = Depends(kyc_decide)):
    return _decide(case_id, "escalate", "escalated", body, ESCALATE_REASON_CODES, user)


@router.post("/cases/{case_id}/notes", response_model=NoteOut)
def add_note(case_id: int, body: NoteRequest, user: dict = Depends(kyc_decide)):
    text = body.body.strip()
    if not text:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Note body is empty")
    repo = get_repository()
    with repo.transaction() as tx:
        if repo.get_case(case_id, tx) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")
        row = repo.add_note(tx, case_id, user["username"], text)
        repo.write_audit(
            tx,
            actor=user["username"],
            action="kyc.add_note",
            entity="kyc_case",
            entity_id=case_id,
            after={"note": text},
        )
    return NoteOut(**row)
