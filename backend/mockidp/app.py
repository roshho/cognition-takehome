"""Mock OIDC provider — issues real RS256-signed JWTs for local dev.

Implements just enough of the OpenID Connect authorization-code flow for
the portal backend to exercise its OIDC client path end to end:
discovery, authorize (user picker instead of credentials), token, JWKS,
userinfo. The issuer string comes from IDP_ISSUER so the `iss` claim can
differ from the URL the backend fetches (docker DNS vs localhost).

Dev only — RSA key is ephemeral and users are hardcoded below.
"""
import base64
import os
import secrets
import time

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

# username -> (display_name, idp groups). Groups map to portal roles via
# portal_platform.rbac.group_role_map.
IDP_USERS = {
    "rana": ("Rana Alvarez", ["kyc_reviewer"]),
    "kwon": ("Min-Jae Kwon", ["kyc_reviewer"]),
    "priya": ("Priya Natarajan", ["kyc_admin"]),
    "marco": ("Marco Reyes", ["read_only"]),
}

_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_kid = "mockidp-key-1"
_codes: dict[str, dict] = {}
_access: dict[str, dict] = {}

app = FastAPI(title="Meridian mock IdP", docs_url=None, redoc_url=None)


def _issuer(request: Request) -> str:
    return os.environ.get("IDP_ISSUER", "").rstrip("/") or str(request.base_url).rstrip("/")


def _b64u(n: int) -> str:
    return base64.urlsafe_b64encode(n.to_bytes((n.bit_length() + 7) // 8, "big")).rstrip(b"=").decode()


@app.get("/.well-known/openid-configuration")
def discovery(request: Request):
    iss = _issuer(request)
    return {
        "issuer": iss,
        "authorization_endpoint": f"{iss}/authorize",
        "token_endpoint": f"{iss}/token",
        "jwks_uri": f"{iss}/jwks",
        "userinfo_endpoint": f"{iss}/userinfo",
        "response_types_supported": ["code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
    }


@app.get("/jwks")
def jwks():
    pub = _key.public_key().public_numbers()
    return {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "kid": _kid,
                "n": _b64u(pub.n),
                "e": _b64u(pub.e),
            }
        ]
    }


@app.get("/authorize", response_class=HTMLResponse)
def authorize(
    request: Request,
    client_id: str,
    redirect_uri: str,
    response_type: str = "code",
    scope: str = "openid",
    state: str = "",
    user: str | None = None,
):
    if response_type != "code":
        return HTMLResponse("unsupported response_type", status_code=400)
    if user is None:
        base = request.url.include_query_params()
        items = "".join(
            f'<li><a href="{base}&user={u}">{d} ({u})</a></li>'
            for u, (d, g) in IDP_USERS.items()
        )
        return HTMLResponse(
            f"<html><body style='font-family:serif;background:#f7f5ee;padding:40px'>"
            f"<h2>Mock IdP — pick a user</h2><ul>{items}</ul></body></html>"
        )
    if user not in IDP_USERS:
        return HTMLResponse("unknown user", status_code=400)
    code = secrets.token_urlsafe(24)
    _codes[code] = {"sub": user, "client_id": client_id, "exp": time.time() + 120}
    sep = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(f"{redirect_uri}{sep}code={code}&state={state}")


class TokenForm(BaseModel):
    grant_type: str
    code: str | None = None


@app.post("/token")
async def token(request: Request):
    form = await request.form()
    grant_type = form.get("grant_type")
    code = form.get("code")
    if grant_type != "authorization_code" or not code:
        return {"error": "unsupported_grant_type"}
    entry = _codes.pop(code, None)
    if entry is None or time.time() > entry["exp"]:
        return {"error": "invalid_grant"}
    username = entry["sub"]
    display, groups = IDP_USERS[username]
    iss = _issuer(request)
    now = int(time.time())
    access = secrets.token_urlsafe(24)
    _access[access] = {"sub": username, "exp": now + 3600}
    id_token = jwt.encode(
        {
            "iss": iss,
            "sub": username,
            "aud": entry["client_id"],
            "iat": now,
            "exp": now + 3600,
            "preferred_username": username,
            "name": display,
            "groups": groups,
        },
        _key,
        algorithm="RS256",
        headers={"kid": _kid},
    )
    return {
        "access_token": access,
        "token_type": "Bearer",
        "expires_in": 3600,
        "id_token": id_token,
    }


@app.get("/userinfo")
def userinfo(request: Request):
    auth = request.headers.get("authorization", "")
    token = auth.removeprefix("Bearer ").strip()
    entry = _access.get(token)
    if entry is None or time.time() > entry["exp"]:
        return {"error": "invalid_token"}
    display, groups = IDP_USERS[entry["sub"]]
    return {"sub": entry["sub"], "preferred_username": entry["sub"], "name": display, "groups": groups}
