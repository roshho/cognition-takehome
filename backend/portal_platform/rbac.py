"""Role-based access control — pure logic, no FastAPI dependency.

Roles come from IdP group claims (see oidc.py) or the seeded user row.
``require_permission`` in the app layer wraps ``has_permission`` into a
FastAPI dependency so every endpoint enforces server-side, not just in UI.
"""
from .config import group_role_map

# role -> permission set. "*" is wildcard (admin).
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {"*"},
    "reviewer": {
        "kyc.read", "kyc.decide", "kyc.unmask",
        "refunds.read", "refunds.decide",
        "flags.read", "flags.toggle",
        "audit.read",
    },
    "read_only": {
        "kyc.read", "refunds.read", "flags.read", "audit.read",
    },
}

# Admin-only extras checked on top of role:
#   refunds.decide_large — refunds over the admin threshold
#   flags.toggle_prod    — production flag toggles
ROLE_PERMISSIONS["admin"].update({"directory.read"})


def has_permission(role: str, permission: str) -> bool:
    perms = ROLE_PERMISSIONS.get(role, set())
    return "*" in perms or permission in perms


def role_for_groups(groups: list[str]) -> str:
    """Map IdP group claims to a portal role. First match wins; default
    read_only so an authenticated-but-unmapped user can look but not touch."""
    mapping = group_role_map()
    for g in groups or []:
        if g in mapping:
            return mapping[g]
    return "read_only"
