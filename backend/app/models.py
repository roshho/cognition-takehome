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
