from typing import Literal

from pydantic import BaseModel


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: str


class LoginRequest(BaseModel):
    username: str


class LoginResponse(BaseModel):
    token: str
    user: UserOut


class UpdateProfileRequest(BaseModel):
    display_name: str


class ToolOut(BaseModel):
    id: str
    name: str
    description: str
    path: str
    roles: list[str]


class AuditEntryOut(BaseModel):
    id: int
    actor: str
    action: str
    entity: str
    entity_id: str | None
    before: str | None
    after: str | None
    created_at: str
    request_id: str | None = None


class StatOut(BaseModel):
    label: str
    value: int | str
    tone: Literal["warn", "danger"] | None = None


class DashboardSummary(BaseModel):
    # tool id -> stats from that tool's registered summary()
    stats: dict[str, list[StatOut]]
    recent_activity: list[AuditEntryOut]
