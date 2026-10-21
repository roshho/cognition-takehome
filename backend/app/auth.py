import secrets
from typing import Callable

from fastapi import Depends, Header, HTTPException, status

from portal_platform.rbac import has_permission

from .db import get_db


def create_session(conn, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    conn.execute("INSERT INTO sessions (token, user_id) VALUES (?, ?)", (token, user_id))
    return token


def get_current_user(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing or invalid Authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    with get_db() as conn:
        row = conn.execute(
            "SELECT u.id, u.username, u.display_name, u.role FROM sessions s "
            "JOIN users u ON u.id = s.user_id WHERE s.token = ?",
            (token,),
        ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")
    return dict(row)


def require_role(*roles: str) -> Callable:
    def dependency(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Role '{user['role']}' is not allowed to perform this action",
            )
        return user

    return dependency


def require_permission(permission: str) -> Callable:
    """RBAC enforcement — every endpoint picks its permission; the backend
    checks it server-side on every call (UI hiding is only cosmetic)."""
    def dependency(user: dict = Depends(get_current_user)) -> dict:
        if not has_permission(user["role"], permission):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Role '{user['role']}' lacks permission '{permission}'",
            )
        return user

    return dependency
