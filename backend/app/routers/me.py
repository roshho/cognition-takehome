from fastapi import APIRouter, Depends

from ..audit import write_audit
from ..auth import get_current_user
from ..db import get_db
from ..models import UpdateProfileRequest, UserOut

router = APIRouter(prefix="/api/me", tags=["me"])


@router.get("", response_model=UserOut)
def get_me(user: dict = Depends(get_current_user)):
    return UserOut(**user)


@router.patch("", response_model=UserOut)
def update_me(body: UpdateProfileRequest, user: dict = Depends(get_current_user)):
    """Rename yourself — a tiny mutating endpoint so Phase 1 can prove the
    audit helper end-to-end."""
    with get_db() as conn:
        before = dict(
            conn.execute(
                "SELECT display_name FROM users WHERE id = ?", (user["id"],)
            ).fetchone()
        )
        conn.execute("UPDATE users SET display_name = ? WHERE id = ?", (body.display_name, user["id"]))
        write_audit(
            conn,
            actor=user["username"],
            action="user.update_display_name",
            entity="user",
            entity_id=user["id"],
            before=before,
            after={"display_name": body.display_name},
        )
        row = conn.execute(
            "SELECT id, username, display_name, role FROM users WHERE id = ?", (user["id"],)
        ).fetchone()
    return UserOut(**dict(row))
