from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth import require_permission
from portal_platform.db import register_schema, register_seed
from portal_platform.rbac import has_permission, register_permissions
from portal_platform.repository import get_repository, register_adapter
from portal_platform.tools import register_tool

from .domain import ENVIRONMENTS, SCHEMA, seed_flags
from .repository import SqlFlagsRepository

APP = "flags"

register_schema(APP, SCHEMA)
register_seed(APP, seed_flags)
# flags.toggle_prod is admin-only: never granted here.
register_permissions({
    "reviewer": {"flags.read", "flags.toggle"},
    "read_only": {"flags.read"},
})
register_adapter(APP, "sql", SqlFlagsRepository)


def _summary(user: dict) -> list[dict]:
    flags = get_repository(APP).list()
    return [
        {"label": "Flags", "value": len(flags)},
        {"label": "On in dev", "value": sum(f["enabled_dev"] for f in flags)},
        {"label": "On in prod", "value": sum(f["enabled_prod"] for f in flags)},
    ]


register_tool(
    "feature-flags",
    name="Feature flags",
    description="Toggle flags per environment; every change lands in the audit log.",
    path="/flags",
    roles=["reviewer", "admin", "read_only"],
    order=30,
    summary=_summary,
)

router = APIRouter(prefix="/api/flags", tags=["flags"])

flags_read = require_permission("flags.read")
flags_toggle = require_permission("flags.toggle")
flags_toggle_prod = require_permission("flags.toggle_prod")


class FlagOut(BaseModel):
    id: int
    key: str
    description: str
    enabled_dev: bool
    enabled_staging: bool
    enabled_prod: bool


class ToggleRequest(BaseModel):
    environment: str


class FlagHistoryEntry(BaseModel):
    id: int
    actor: str
    action: str
    before: str | None
    after: str | None
    created_at: str


@router.get("", response_model=list[FlagOut])
def list_flags(user: dict = Depends(flags_read)):
    return get_repository(APP).list()


@router.post("/{key}/toggle", response_model=FlagOut)
def toggle(key: str, body: ToggleRequest, user: dict = Depends(flags_toggle)):
    env = body.environment
    if env not in ENVIRONMENTS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"environment must be one of: {', '.join(ENVIRONMENTS)}",
        )
    # prod toggles need the flags.toggle_prod permission (admin-only
    # by default); dev/staging are open to anyone with flags.toggle.
    if env == "prod" and not has_permission(user["role"], "flags.toggle_prod"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Toggling production flags requires an admin",
        )
    col = f"enabled_{env}"
    repo = get_repository(APP)
    with repo.transaction() as tx:
        flag = repo.get(key, tx)
        if flag is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Flag not found")
        new_val = not flag[col]
        repo.update(tx, key, {col: int(new_val)})
        repo.write_audit(
            tx,
            actor=user["username"],
            action="flag.toggle",
            entity="feature_flag",
            entity_id=key,
            before={env: bool(flag[col])},
            after={env: bool(new_val)},
        )
        updated = repo.get(key, tx)
    return updated


@router.get("/{key}/history", response_model=list[FlagHistoryEntry])
def history(key: str, user: dict = Depends(flags_read)):
    """Change history for a flag — straight from the shared audit log."""
    rows = get_repository(APP).audit_history("feature_flag", key)
    return [FlagHistoryEntry(**r) for r in rows]
