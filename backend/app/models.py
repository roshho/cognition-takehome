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


class KycDashboard(BaseModel):
    open_cases: int
    sla_breached: int
    high_risk_open: int
    assigned_to_me: int


class RefundsDashboard(BaseModel):
    pending_count: int
    pending_amount_cents: int
    over_threshold_pending: int


class FlagsDashboard(BaseModel):
    total: int
    enabled: dict[str, int]


class DashboardSummary(BaseModel):
    kyc: KycDashboard | None = None
    refunds: RefundsDashboard | None = None
    flags: FlagsDashboard | None = None
    recent_activity: list[AuditEntryOut]
