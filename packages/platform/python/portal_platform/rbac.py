"""Role-based access control — pure logic, no FastAPI dependency.

Roles come from IdP group claims (see oidc.py) or the seeded user row.
``require_permission`` in the app layer wraps ``has_permission`` into a
FastAPI dependency so every endpoint enforces server-side, not just in UI.
"""
from .config import group_role_map

# role -> permission set. "*" is wildcard (admin).
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {"*"},
    "reviewer": {"audit.read"},
    "read_only": {"audit.read"},
}
# Each app grants its own permissions at import via register_permissions
# (see apps/*/backend/router.py). Admin-only permissions are simply never
# granted to other roles (e.g. refunds.decide_large, flags.toggle_prod,
# directory.read).


def register_permissions(grants: dict[str, set[str]]) -> None:
    """Let an app grant its own permissions at import time.

    Example: ``register_permissions({"reviewer": {"assets.read", "assets.write"},
    "read_only": {"assets.read"}})``. Admins already have "*" and need no grant.
    """
    for role, perms in grants.items():
        ROLE_PERMISSIONS.setdefault(role, set()).update(perms)


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
