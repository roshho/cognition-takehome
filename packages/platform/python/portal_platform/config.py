"""Environment-driven configuration — nothing tenant-specific is hardcoded."""
import json
import os

# --- OIDC ---
# OIDC_ISSUER is the *public* issuer: the browser is redirected to it and it
# must match the `iss` claim on tokens. OIDC_INTERNAL_ISSUER is where the
# backend talks to the IdP (defaults to the public one) — needed because in
# docker the browser uses localhost while the backend resolves `idp`.
OIDC_ISSUER = os.environ.get("OIDC_ISSUER", "").rstrip("/")
OIDC_INTERNAL_ISSUER = os.environ.get("OIDC_INTERNAL_ISSUER", OIDC_ISSUER).rstrip("/")
OIDC_CLIENT_ID = os.environ.get("OIDC_CLIENT_ID", "portal")
OIDC_CLIENT_SECRET = os.environ.get("OIDC_CLIENT_SECRET", "")
OIDC_SCOPE = os.environ.get("OIDC_SCOPE", "openid profile groups")
# Frontend origin the callback redirects to after creating the session.
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173").rstrip("/")
OIDC_REDIRECT_URI = os.environ.get("OIDC_REDIRECT_URI", "")


def oidc_configured() -> bool:
    return bool(OIDC_ISSUER)


def oidc_redirect_uri() -> str:
    return OIDC_REDIRECT_URI or f"{OIDC_INTERNAL_ISSUER or OIDC_ISSUER}/unused"


# IdP group claim -> portal role. Override wholesale with OIDC_GROUP_MAP_JSON.
DEFAULT_GROUP_ROLE_MAP = {
    "kyc_admin": "admin",
    "kyc_reviewer": "reviewer",
    "read_only": "read_only",
}


def group_role_map() -> dict[str, str]:
    raw = os.environ.get("OIDC_GROUP_MAP_JSON")
    if raw:
        try:
            return {str(k): str(v) for k, v in json.loads(raw).items()}
        except Exception:
            pass
    return dict(DEFAULT_GROUP_ROLE_MAP)


# --- data adapter ---
# "sql" (local sqlite, real) or "dataverse" (OData Web API, env-authed).
DATA_ADAPTER = os.environ.get("DATA_ADAPTER", "sql").lower()


def data_adapter_for(app: str, available: set[str] | None = None) -> str:
    """Adapter kind for one app. ``DATA_ADAPTER_<APP>`` (e.g.
    DATA_ADAPTER_KYC=dataverse) is explicit and must exist for that app.
    The global ``DATA_ADAPTER`` applies only to apps that ship that kind;
    others stay on "sql"."""
    per_app = os.environ.get("DATA_ADAPTER_" + app.upper().replace("-", "_"))
    if per_app:
        return per_app.lower()
    kind = os.environ.get("DATA_ADAPTER", "sql").lower()
    if available is not None and kind not in available:
        return "sql"
    return kind

DATAVERSE_BASE_URL = os.environ.get("DATAVERSE_BASE_URL", "").rstrip("/")
DATAVERSE_ENTITY = os.environ.get("DATAVERSE_ENTITY", "mer_kyccases")
DATAVERSE_API = os.environ.get("DATAVERSE_API", "api/data/v9.2")
DATAVERSE_TENANT_ID = os.environ.get("DATAVERSE_TENANT_ID", "")
DATAVERSE_CLIENT_ID = os.environ.get("DATAVERSE_CLIENT_ID", "")
DATAVERSE_CLIENT_SECRET = os.environ.get("DATAVERSE_CLIENT_SECRET", "")
DATAVERSE_TOKEN_URL = os.environ.get(
    "DATAVERSE_TOKEN_URL",
    f"https://login.microsoftonline.com/{DATAVERSE_TENANT_ID}/oauth2/v2.0/token"
    if DATAVERSE_TENANT_ID
    else "",
)
