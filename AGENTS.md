# AGENTS.md: Meridian internal-tools portal

Prototype showing that engineers can build internal tools as normal code.
FastAPI + SQLite backend, React + TS frontend, npm workspaces.

## Repo layout

- `apps/<name>/`: one self-contained internal app per directory. The
  built-ins are `kyc`, `refunds` and `flags`; `it-assets` is the reference
  generated app. Each app has:
  - `backend/router.py`: endpoints plus import-time registrations (schema,
    seed, permissions, adapters, home-page tool);
  - `backend/repository.py`: the app's repository and SQL adapter;
  - optional `backend/domain.py`: constants, helpers, seed data;
  - `backend/test_<name>.py`;
  - `frontend/Page.tsx`, which exports `meta`.

  `apps/conftest.py` re-exports the shared `client` / `login` fixtures.
- `backend/app/`: portal core: sessions, mock login, OIDC routes, users, the
  audit trail, the dashboard (`routers/core.py`), and `main.py`, which mounts
  the apps.
- `packages/platform/python/portal_platform/`: shared backend package,
  installed with `pip install -e` (no `sys.path` hacks):
  - `rbac.py`: `register_permissions`;
  - `audit.py`: `write_audit`, plus request-id middleware;
  - `db.py`: `register_schema`, `register_seed`, `connect`;
  - `repository.py`: `register_adapter`, `get_repository`;
  - `adapters/sql.py`: `SqlRepository`;
  - `adapters/dataverse.py`: `DataverseClient`;
  - `tools.py`: `register_tool`;
  - `oidc.py`, `config.py`.
- `packages/platform/web/`: the `@portal/platform` npm package: `AppShell`,
  `DataTable`, `Form`/`FormField`, `RequireAuth`/`RequireRole`,
  `useAuth`, `untypedApi`.
- `frontend/src/`: the React shell. `@portal/api` is the typed client
  generated from `backend/openapi.json`. `apps.ts` globs the app pages.
- `templates/internal-app/`: the template the generator copies.
- `backend/mockidp/`: local OIDC provider (the docker-compose `idp` service).

## Create a new app

```bash
npm run new-app -- <app-name>   # lowercase letters, digits, hyphens
```

Then restart `npm start`. No wiring edits are needed:
- `app/main.py::_mount_apps` imports each `apps/<name>/backend/` as the
  package `portal_apps.<name>` (hyphens become `_`), so relative imports work.
- `frontend/src/apps.ts` routes each `apps/*/frontend/Page.tsx` at
  `meta.path` and `meta.path/*` (use nested `<Routes>` for sub-pages).
- The home-page card and its stats come from `register_tool(...)` in
  `router.py`.

## Required conventions

- **RBAC:** every endpoint declares
  `Depends(require_permission("<app>.<verb>"))`. Grant permissions with
  `register_permissions` at import. Admin-only permissions are simply never
  granted. UI hiding is cosmetic; the backend enforces.
- **Audit:** every mutation calls `repo.write_audit(tx, ...)` inside the same
  `with repo.transaction() as tx:` block as the change. UPDATE/DELETE on
  `audit_log` are rejected at the driver level.
- **Data:** routers never call `get_db()` or write SQL. All data goes through
  `get_repository(APP)`:
  - register at least a `"sql"` adapter (subclass `SqlRepository` and set
    `table`, `columns` and `key`);
  - add other kinds, such as `"dataverse"`, with `register_adapter`;
  - define tables with `register_schema` and seed data with `register_seed`.
- **Input:** all request bodies are pydantic models (FastAPI returns 422).
  Never interpolate user input into SQL: identifiers come from code, values
  are parameterized.
- **Frontend:**
  - use `@portal/platform` components;
  - use `@portal/api` (typed) or `untypedApi` for HTTP calls;
  - export `meta` from `Page.tsx` with `path` and `roles`, mirroring the
    backend grants.
- No secrets in the repo; all configuration comes from env vars (see the
  README env table).

## Commands

```bash
npm run setup      # venv + platform editable install + npm install + gen:api
npm start          # api :8000 (reloads on backend/, apps/, packages/), web :5173
npm test           # pytest backend/tests + apps/*/backend
npm run gen:api    # openapi.json -> frontend/src/api/schema.d.ts
docker compose up --build   # api :8000, web :3000, mock IdP :9000
```

## Definition of done

- [ ] `npm test` is green, including the app's `test_<name>.py` (403 for
      read_only, an audit row per mutation, 422 on bad input, repository
      contract).
- [ ] Every endpoint has `require_permission`, every mutation is audited,
      all data goes through the repository, and inputs are pydantic models.
- [ ] `npm run build --workspace frontend` is clean (tsc type-checks
      `apps/*/frontend` too).
- [ ] `npm run gen:api` was rerun if the API surface changed.
- [ ] README and AGENTS.md are updated if conventions or layout changed.
