"""OIDC authorization-code flow against a configurable issuer.

Discovery + JWKS come from the issuer at runtime — no hardcoded tenant.
``OIDC_ISSUER`` is the public issuer (browser redirect + `iss` claim);
``OIDC_INTERNAL_ISSUER`` is where the backend reaches the IdP (defaults to
the public one — needed when docker DNS names differ from the browser's).
"""
import secrets
import time
from urllib.parse import urlencode

import httpx
import jwt
from jwt import PyJWKClient

from . import config
from .rbac import role_for_groups

_discovery: dict | None = None
_discovery_at: float = 0.0
_jwks: PyJWKClient | None = None
_states: dict[str, float] = {}


def _http() -> httpx.Client:
    return httpx.Client(timeout=10.0)


def discovery() -> dict:
    global _discovery, _discovery_at, _jwks
    now = time.time()
    if _discovery and now - _discovery_at < 300:
        return _discovery
    base = config.OIDC_INTERNAL_ISSUER
    with _http() as c:
        doc = c.get(f"{base}/.well-known/openid-configuration").json()
    _discovery = doc
    _discovery_at = now
    _jwks = PyJWKClient(doc["jwks_uri"])
    return doc


def new_state() -> str:
    state = secrets.token_urlsafe(24)
    _states[state] = time.time() + 600
    return state


def consume_state(state: str) -> bool:
    exp = _states.pop(state, None)
    return exp is not None and time.time() < exp


def authorization_url(state: str) -> str:
    doc = discovery()
    q = urlencode(
        {
            "client_id": config.OIDC_CLIENT_ID,
            "redirect_uri": _redirect_uri(),
            "response_type": "code",
            "scope": config.OIDC_SCOPE,
            "state": state,
        }
    )
    return f"{doc['authorization_endpoint']}?{q}"


def _redirect_uri() -> str:
    return config.OIDC_REDIRECT_URI or ""


def exchange_code(code: str) -> dict:
    """Exchange the auth code at the token endpoint and verify the id_token
    signature + issuer + audience against the issuer's JWKS."""
    doc = discovery()
    with _http() as c:
        tok = c.post(
            doc["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "client_id": config.OIDC_CLIENT_ID,
                "client_secret": config.OIDC_CLIENT_SECRET,
                "redirect_uri": _redirect_uri(),
                "code": code,
            },
        )
    tok.raise_for_status()
    body = tok.json()
    id_token = body["id_token"]
    key = _jwks.get_signing_key_from_jwt(id_token).key
    return jwt.decode(
        id_token,
        key,
        algorithms=["RS256", "ES256"],
        audience=config.OIDC_CLIENT_ID,
        issuer=config.OIDC_ISSUER,
    )


def claims_to_identity(claims: dict) -> tuple[str, str, str]:
    """OIDC claims -> (username, display_name, role)."""
    username = claims.get("preferred_username") or claims.get("sub") or "unknown"
    display = claims.get("name") or username
    role = role_for_groups(claims.get("groups") or [])
    return username, display, role
