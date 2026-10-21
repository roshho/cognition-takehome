"""It Assets — internal app generated from templates/internal-app.

Conventions (AGENTS.md): every endpoint uses require_permission(...);
every mutation writes an audit row inside the same repo.transaction();
all data goes through the app's repository (repository.py), selected via
get_repository(APP); input is validated with pydantic.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth import require_permission
from portal_platform.db import register_schema
from portal_platform.rbac import register_permissions
from portal_platform.repository import get_repository, register_adapter
from portal_platform.tools import register_tool

from .repository import TABLE, SqlItAssetsRepository

APP = "it-assets"

register_schema(
    APP,
    f"""
    CREATE TABLE IF NOT EXISTS {TABLE} (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed')),
        owner TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT
    );
    """,
)

# Role grants for this app (admin already has "*").
register_permissions({
    "reviewer": {f"{APP}.read", f"{APP}.write"},
    "read_only": {f"{APP}.read"},
})

register_adapter(APP, "sql", SqlItAssetsRepository)


def _summary(user: dict) -> list[dict]:
    return [{"label": "Open", "value": len(get_repository(APP).list(status="open"))}]


# Home-page card; roles mirror the grants above (backend still enforces).
register_tool(
    APP,
    name="It Assets",
    description="Generated internal app — edit me.",
    path="/apps/it-assets",
    roles=["reviewer", "admin", "read_only"],
    summary=_summary,
)

router = APIRouter(prefix=f"/api/{APP}", tags=[APP])


class ItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ItemOut(BaseModel):
    id: int
    name: str
    status: str
    owner: str | None
    created_at: str
    updated_at: str | None


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


@router.get("/items", response_model=list[ItemOut])
def list_items(user: dict = Depends(require_permission(f"{APP}.read"))):
    return get_repository(APP).list()


@router.post("/items", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
def create_item(body: ItemIn, user: dict = Depends(require_permission(f"{APP}.write"))):
    repo = get_repository(APP)
    with repo.transaction() as tx:
        item = repo.insert(tx, {"name": body.name, "owner": user["username"]})
        repo.write_audit(tx, actor=user["username"], action=f"{APP}.create",
                         entity=TABLE, entity_id=item["id"], before=None, after=item)
    return item


@router.post("/items/{item_id}/close", response_model=ItemOut)
def close_item(item_id: int, user: dict = Depends(require_permission(f"{APP}.write"))):
    repo = get_repository(APP)
    with repo.transaction() as tx:
        before = repo.get(item_id, tx)
        if before is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "item not found")
        repo.update(tx, item_id, {"status": "closed", "updated_at": _now()})
        after = repo.get(item_id, tx)
        repo.write_audit(tx, actor=user["username"], action=f"{APP}.close",
                         entity=TABLE, entity_id=item_id, before=before, after=after)
    return after
