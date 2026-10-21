# Meridian Internal Tools Portal — proof of concept

A small, runnable prototype showing that engineers at a fintech could build
internal tools as **normal code** instead of using a low-code platform.

- **Backend:** FastAPI + SQLite, seeded mock data, OpenAPI spec at `/openapi.json`
  (stands in for the company's existing internal APIs).
- **Frontend:** React + TypeScript. The API client (`src/api/schema.d.ts`) is
  generated from the OpenAPI spec — no hand-written types.

## Run it

```bash
npm install        # installs root tooling, backend deps, frontend deps
npm run gen:api    # generate the typed client from the OpenAPI spec (once, or after API changes)
npm start          # api on :8000, web on :5173
```

or, with Docker:

```bash
docker compose up --build   # api on :8000, web on :3000
```

Open http://localhost:5173 (or :3000 with docker). Sign in as a seeded user —
no password:

| User      | Role     |
| --------- | -------- |
| `rana`    | reviewer |
| `kwon`    | reviewer |
| `priya`   | admin    |

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

**Phase 3 — refunds dashboard + feature-flag panel** — not built yet.

## Mocked vs. production

| Mocked here                          | Production would need                        |
| ------------------------------------ | -------------------------------------------- |
| Pick-a-user login, bearer tokens     | Real SSO (OIDC/SAML), session management     |
| SQLite file                          | Postgres, migrations, backups                |
| Role list hardcoded on `users.role`  | RBAC from an identity provider / directory   |
| Audit log in app DB                  | Tamper-evident store (WORM / immutable logs) |
| `docker compose` for local dev       | Hosting, deploys, secrets management         |
| PII "masking" string surgery         | Field-level encryption + access policies     |
| Placeholder documents                | Real document storage + viewers              |
| Seeded sanctions/PEP hits            | Real screening vendor integration            |

## Known limitations

- Sessions never expire; logout just deletes the token.
- Audit log has no tamper protection — a DB write can edit history.
- No document storage, no real screening vendors, no compliance certifications,
  no app-building UI for non-engineers (all out of scope by design).

## Layout

```
backend/app/        FastAPI app (auth, audit, tools, routers)
backend/tests/      pytest: role enforcement, audit logging
frontend/src/       React app (generated client, shared components, pages)
```

## Tests

```bash
npm test   # backend pytest
```
