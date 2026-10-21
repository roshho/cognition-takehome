from fastapi import APIRouter, Depends, Header, HTTPException, status

from ..audit import write_audit
from ..auth import create_session, get_current_user
from ..db import get_db
from ..models import LoginRequest, LoginResponse, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest):
    """Mock login: pick a seeded username, get a session token.

    No password — this stands in for the company's real SSO.
    """
    with get_db() as conn:
        user = conn.execute(
            "SELECT id, username, display_name, role FROM users WHERE username = ?",
            (body.username,),
        ).fetchone()
        if user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user")
        token = create_session(conn, user["id"])
        write_audit(
            conn,
            actor=user["username"],
            action="auth.login",
            entity="session",
            entity_id=None,
            after={"username": user["username"], "role": user["role"]},
        )
    return LoginResponse(token=token, user=UserOut(**dict(user)))


@router.post("/logout")
def logout(
    authorization: str | None = Header(default=None),
    user: dict = Depends(get_current_user),
):
    token = authorization.removeprefix("Bearer ").strip() if authorization else ""
    with get_db() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        write_audit(conn, actor=user["username"], action="auth.logout", entity="session")
    return {"ok": True}


@router.get("/users", response_model=list[UserOut])
def list_login_users():
    """Seeded users to show on the mock login screen. No auth needed —
    production would render an SSO page instead."""
    with get_db() as conn:
        rows = conn.execute("SELECT id, username, display_name, role FROM users ORDER BY id").fetchall()
    return [UserOut(**dict(r)) for r in rows]
