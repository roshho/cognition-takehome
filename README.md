# Meridian Internal Tools Portal — proof of concept

A small, runnable prototype showing that engineers at a fintech could build
internal tools as **normal code** instead of using a low-code platform.

- **Backend:** FastAPI + SQLite, seeded mock data, OpenAPI spec at `/openapi.json`
  (stands in for the company's existing internal APIs).
- **Frontend:** React + TypeScript. The API client (`src/api/schema.d.ts`) is
  generated from the OpenAPI spec — no hand-written types.

## Run it

```bash
npm run setup      # venv + platform editable install + npm install + gen:api
npm start          # api on :8000, web on :5173
```

Create a new internal app in one command — see AGENTS.md:

```bash
npm run new-app -- <app-name>   # generates apps/<name>/, auto-mounted on restart
```

or, with Docker:

```bash
docker compose up --build   # api on :8000, web on :3000, mock OIDC provider on :9000
```

Open http://localhost:5173 (or :3000 with docker). Two ways in:

- **Dev login** — pick a seeded user, no password.
- **Sign in with company SSO** — OIDC authorization-code flow. Locally this
  goes to the in-repo mock IdP (also shown on the login page with the SSO
  button). The mock shows a user picker instead of a password prompt.

| User      | IdP groups    | Role      |
| --------- | ------------- | --------- |
| `rana`    | `kyc_reviewer`| reviewer  |
| `kwon`    | `kyc_reviewer`| reviewer  |
| `priya`   | `kyc_admin`   | admin     |
| `marco`   | `read_only`   | read_only |

## What is NOT built / mocked (out of scope)

- Real SSO against a corporate IdP — OIDC is implemented and configurable,
  but only exercised against the in-repo mock provider
- Hosting/deploy — only local `npm start` or `docker compose`
- Document storage — KYC documents are filename placeholders
- Real screening vendors — sanctions/PEP hits are seeded rows
- Compliance certifications
- Any app-building UI for non-engineers — the whole point is code-first tools

## What's built

**Phase 1 — foundation (current state)**

- Mock login with `reviewer` and `admin` roles. Roles are enforced in FastAPI
  dependencies (`require_role`), not just hidden in the UI.
- Append-only `audit_log` table written through one shared helper
  (`app/audit.py::write_audit`) on the same DB connection as each mutation.
- Shared frontend: `AppShell` (layout), `DataTable` (sort/filter),
  `Form`/`FormField`, `RequireAuth`/`RequireRole` route guards.
- Portal home lists tools filtered by role (`GET /api/tools`). Phase 1 ships
  two tools: **User directory** (admin only) and **Audit trail** (admins see
  everything, reviewers see their own actions).
- `PATCH /api/me` (rename yourself) exists as a minimal mutating endpoint so
  the audit path is exercised end-to-end.

**Phase 2 — KYC review queue (current state)**

- Queue at `/kyc`: 25 seeded cases, filterable by status and risk band,
  SLA-breach highlighting (open > 48h), sorted breach-first then by risk.
- Case detail at `/kyc/:id`: applicant info with PII masked by default
  (`POST .../unmask` reveals it and is written to the audit log), placeholder
  documents, risk score, mock sanctions/PEP hits, notes.
- Actions: assign to me, approve, reject, escalate — all audited. Reject and
  escalate require a reason code (validated against a fixed list, 422
  otherwise). High-risk cases (score ≥ 70) need two distinct approvers — the
  four-eyes rule; the same user approving twice gets a 409.
- Only `open` cases can be actioned (409 otherwise).

**Phase 3 — refunds dashboard + feature-flag panel (current state)**

- Refunds at `/refunds`: 16 seeded refunds, summary stat cards, filters by
  status and amount range, approve/deny — all audited. Refunds ≥ $10,000
  (`ADMIN_THRESHOLD_CENTS`) can only be decided by an admin; reviewers get 403
  and the buttons are disabled.
- Flags at `/flags`: 6 seeded flags with per-environment toggles
  (dev/staging/prod). Prod toggles are admin-only (403 for reviewers);
  dev/staging are open to both roles. Clicking a flag shows its change
  history, read straight from `audit_log` (`entity = 'feature_flag'`).
- Both tools reuse the Phase 1 `DataTable`, role guards, and `write_audit`
  helper — no shared-code changes were needed beyond Phase 2's
  `rowClassName` prop.

**Production-shaped layer (`packages/platform/python/portal_platform/`)**

The shared package other apps would import; the app code consumes it:

- **OIDC auth** (`portal_platform/oidc.py`, `config.py`) — authorization-code
  flow against any issuer configured purely by env vars (nothing tenant-
  specific hardcoded). `GET /api/auth/oidc/login` redirects to the IdP,
  `/api/auth/oidc/callback` exchanges the code and verifies the RS256
  `id_token` signature via the discovered JWKS, then mints the same session
  token the rest of the app already uses.
- **Mock OIDC provider** (`backend/mockidp/`) — a tiny FastAPI IdP with
  discovery, JWKS, authorize (user picker) and token endpoints, issuing real
  RS256 tokens. Runs as the `idp` service in docker-compose.
- **Group-claim → role mapping** (`portal_platform/rbac.py`) —
  `kyc_admin → admin`, `kyc_reviewer → reviewer`, `read_only → read_only`,
  overrideable via `OIDC_GROUP_MAP_JSON`. Unknown/absent groups get
  `read_only`.
- **Backend RBAC** — every router enforces a permission dependency
  (`require_permission("kyc.decide")` etc.); the UI also hides actions the
  role can't perform but the backend is the enforcement point. `read_only`
  can view every tool but mutates nothing. A user who escalated a case
  cannot later decide it (403); escalated cases are resolvable by admins
  (senior review).
- **Audit hardening** (`portal_platform/audit.py`) — `audit_log` rows now
  carry a `request_id` (set per request by middleware, surfaced as the
  `x-request-id` response header). The SQLite connection sets an
  `authorizer` that makes UPDATE/DELETE on `audit_log` fail — the append-
  only guarantee lives in the DB layer, not convention. Mutations and their
  audit rows commit in one transaction. PII reads (`unmask`) are audited
  like writes.
- **Repository interface** (`portal_platform/repository.py`) — the KYC
  router only talks to a `KycRepository` protocol (`transaction`,
  `list_cases`, `get_case`, `update_case`, `add_approval`, `add_escalation`,
  `has_escalated`, `add_note`, `write_audit`). Two adapters behind
  `DATA_ADAPTER`:
  - `sql` — wraps the existing SQLite database (real).
  - `dataverse` — OData Web API client (`/api/data/v9.2/<entity>`) with
    client-credentials auth from env vars. Tested against `httpx`
    `MockTransport` responses only — never against a real Dataverse.

| Env var                    | Meaning                                              |
| -------------------------- | ---------------------------------------------------- |
| `OIDC_ISSUER`              | Public issuer URL (browser redirects, `iss` claim)   |
| `OIDC_INTERNAL_ISSUER`     | Backend-facing issuer URL (defaults to `OIDC_ISSUER`; in compose it's `http://idp:9000` while browsers use `http://localhost:9000`) |
| `OIDC_CLIENT_ID`           | Client ID registered at the IdP                      |
| `OIDC_CLIENT_SECRET`       | Client secret (not needed for the mock)              |
| `OIDC_REDIRECT_URI`        | Callback URL, default `<issuer>:8000/.../callback`   |
| `OIDC_SCOPE`               | Default `openid profile groups`                      |
| `OIDC_GROUP_MAP_JSON`      | Optional `{"idp_group": "role"}` override            |
| `FRONTEND_ORIGIN`          | Where the callback redirects with `?sso_token=`      |
| `DATA_ADAPTER`             | `sql` (default) or `dataverse`                       |
| `DATAVERSE_BASE_URL`       | e.g. `https://org.crm.dynamics.com`                  |
| `DATAVERSE_ENTITY`         | Table prefix/collection, default `mer_kyccases`      |
| `DATAVERSE_TENANT_ID` / `CLIENT_ID` / `CLIENT_SECRET` / `TOKEN_URL` | Client-credentials for Dataverse |
| `IDP_ISSUER`               | (mock IdP only) issuer value to publish/sign with    |

## Known gaps — read me

Things that are approximated or stubbed, stated plainly:

1. **SQLite has no role grants.** The "app DB role can't UPDATE/DELETE the
   audit table" requirement is enforced with `sqlite3.Connection.set_authorizer`
   — every statement touching `audit_log` that isn't INSERT/SELECT is denied
   at the driver level (test verifies this). Production Postgres:
   `REVOKE UPDATE, DELETE ON audit_log FROM app_role;`.
2. **Dataverse adapter is HTTP-contracted only.** It implements the full
   repository interface over OData and passes the same contract tests as the
   SQL adapter, but against mocked responses — field names (`mer_*`), the
   4-eyes/escalation related-entity shapes, and `$expand` usage are educated
   guesses that would need verification against a real Dataverse environment.
3. **No cross-DB transactions on Dataverse.** SQL adapter writes audit in the
   same sqlite transaction as the mutation. Dataverse Web API has no ambient
   transaction spanning OData calls, so the adapter's transaction shim writes
   audit rows to a local sqlite sidecar; production would use Dataverse's
   `ExecuteTransaction` batch or an outbox.
4. **OIDC state is in-memory.** Fine for one-process dev; multi-replica
   deploys need a shared store or signed cookie.
5. **Dev login remains on.** The pick-a-user endpoint stays enabled so the
   prototype works with zero config; production would gate it behind
   `OIDC_ISSUER` being unset or a dev flag.
6. **Mock IdP issues tokens for any user claim** — it's a password-free
   picker, not an authentication check.
7. **Verified, not stubbed**: the full OIDC round trip was exercised live
   (login → mock IdP → code exchange → RS256/JWKS verification → role
   mapping → session token works on `/api/me`), and `docker compose` was
   validated for build-order correctness; the complete image build wasn't
   re-run due to Docker Hub pull rate-limits on the dev machine.

## Mocked vs. production

| Mocked here                          | Production would need                        |
| ------------------------------------ | -------------------------------------------- |
| Pick-a-user dev login + bearer tokens| OIDC is in — needs a real IdP + MFA + expiry |
| SQLite file                          | Postgres, migrations, backups                |
| Group→role map in env/defaults       | RBAC driven by the enterprise IdP/directory  |
| Audit log in app DB                  | Tamper-evident store (WORM / immutable logs) |
| `docker compose` for local dev       | Hosting, deploys, secrets management         |
| PII "masking" string surgery         | Field-level encryption + access policies     |
| Placeholder documents                | Real document storage + viewers              |
| Seeded sanctions/PEP hits            | Real screening vendor integration            |

## Known limitations

- Sessions never expire; logout just deletes the token.
- Audit log is append-only at the driver level but not tamper-evident — a
  superuser could still rewrite history (production: WORM storage).
- No document storage, no real screening vendors, no compliance certifications,
  no app-building UI for non-engineers (all out of scope by design).
- `read_only` maps every seeded permission read but nothing write — it sees
  all three tools plus the audit trail, no action buttons.

## Layout

```
backend/app/                  FastAPI app (auth, seed, routers for built-in tools)
backend/mockidp/              mock OIDC provider (discovery, JWKS, RS256 tokens)
backend/tests/                pytest: role enforcement, audit, adapter contracts
packages/platform/python/     portal_platform pip package: config, oidc, rbac,
                              audit, db registry, repository + sql/dataverse adapters
packages/platform/web/        @portal/platform npm package: AppShell, DataTable,
                              Form, RequireAuth/RequireRole, AuthProvider, api client
apps/                         generated apps (self-contained router+page+test);
                              it-assets is the reference example
/templates/internal-app/      template copied by `npm run new-app`
frontend/src/                 React app (generated client, pages, app discovery)
```

AGENTS.md at the repo root documents the conventions generated apps must
follow and how the auto-mount works.

## Tests

```bash
npm test   # pytest backend/tests + apps/*/backend/test_*.py
```
