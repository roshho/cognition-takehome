# AGENTS.md — Meridian internal-tools portal

Prototype proving engineers can build internal tools as normal code.
FastAPI + SQLite backend, React + TS frontend, npm workspaces.

## Repo layout

- `backend/app/` — the portal's FastAPI app: auth/session, seed data, the
  three built-in tools' routers (`app/routers/`), `app/db.py` (core schema).
- `packages/platform/python/portal_platform/` — shared backend package
  (installed with `pip install -e`, never sys.path hacks): `oidc.py`,
  `rbac.py` (permissions + `register_permissions`), `audit.py` (append-only
  audit + request-id middleware), `db.py` (`connect`, `register_schema`,
  `init_db`), `repository.py` + `adapters/` (sql | dataverse).
- `packages/platform/web/` — `@portal/platform` npm package: `AppShell`,
  `DataTable`, `Form`/`FormField`, `RequireAuth`/`RequireRole`,
  `AuthProvider`/`useAuth`, `createPortalClient`/`untypedApi`.
- `apps/<name>/` — generated apps (self-contained: `backend/router.py`,
  `backend/test_<name>.py`, `frontend/Page.tsx`). `apps/conftest.py` has the
  shared pytest fixtures. `apps/it-assets` is the reference generated app.
- `templates/internal-app/` — the template the generator copies.
- `backend/mockidp/` — local OIDC provider (docker-compose `idp` service).

## Create a new app

```bash
npm run new-app -- <app-name>   # lowercase letters, digits, hyphens
```

Then restart `npm start`. No wiring edits: the backend auto-mounts
`apps/*/backend/router.py` (`app/main.py::_mount_generated_apps`) and the
frontend auto-routes `apps/*/frontend/Page.tsx` via `import.meta.glob`
(`frontend/src/apps.ts`), keyed off its exported `meta` object.

## Required conventions

- **RBAC**: every endpoint declares `Depends(require_permission("<app>.<verb>"))`.
  Grant app permissions at module import via `register_permissions` — never
  rely on UI hiding; the backend enforces.
- **Audit**: every mutation calls `write_audit(conn, ...)` inside the same
  `with get_db() as conn:` block as the change (same transaction).
  UPDATE/DELETE on `audit_log` are rejected at the driver level.
- **Data**: apps do not open raw connections to foreign tables — use
  `get_db()` for your own table or a `KycRepository` adapter for KYC data.
  Tables come from `register_schema(name, ddl)` at import, not ad-hoc DDL.
- **Input**: all request bodies are pydantic models — FastAPI returns 422.
  Never interpolate user input into SQL; `TABLE` constants may be
  f-stringed, values are always parameterized.
- **Frontend**: use `@portal/platform` components (`DataTable`, `Form`,
  `untypedApi`, `useAuth`); export `meta` from Page.tsx with `path`,
  `title`, `description`, `roles`.
- No secrets in the repo; config via env vars (see README env table).

## Commands

```bash
npm run setup      # venv + platform editable install + npm install + gen:api
npm start          # api :8000, web :5173
npm test           # pytest backend/tests + apps/*
npm run gen:api    # openapi.json -> frontend/src/api/schema.d.ts
docker compose up --build   # api :8000, web :3000, mock IdP :9000
```

## Definition of done

- [ ] `npm test` green, including the generated app's `test_<name>.py`
      (403 for read_only, audit row per mutation, 422 on bad input).
- [ ] Every new endpoint has `require_permission`; every mutation is
      audited; inputs are pydantic-validated.
- [ ] `npm run build --workspace frontend` clean (tsc + vite).
- [ ] `npm run gen:api` rerun if the API surface changed.
- [ ] README/AGENTS updated if conventions or layout changed.
