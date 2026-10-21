import importlib.util
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from portal_platform.audit import RequestIdMiddleware

from .db import init_db, get_db
from .flags import seed_flags
from .kyc import seed_kyc
from .refunds import seed_refunds
from .routers import auth, core, flags as flags_router, kyc as kyc_router, me, refunds as refunds_router
from .seed import seed

# Generated apps live at <repo>/apps/<name>/backend/router.py (locally) or
# /app/apps/... in the api image. PORTAL_APPS_DIR overrides discovery.
_HERE = Path(__file__).resolve()
APPS_DIR = Path(os.environ["PORTAL_APPS_DIR"]) if os.environ.get("PORTAL_APPS_DIR") else next(
    (p for p in (_HERE.parents[1] / "apps", _HERE.parents[2] / "apps") if p.is_dir()),
    _HERE.parents[2] / "apps",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with get_db() as conn:
        seed(conn)
        seed_kyc(conn)
        seed_refunds(conn)
        seed_flags(conn)
    yield


app = FastAPI(
    title="Meridian Bank Internal APIs",
    version="0.1.0",
    description="Stands in for the company's existing internal APIs. Phase 1: foundation.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8080", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestIdMiddleware)

app.include_router(auth.router)
app.include_router(me.router)
app.include_router(core.router)
app.include_router(kyc_router.router)
app.include_router(refunds_router.router)
app.include_router(flags_router.router)


def _mount_generated_apps() -> None:
    """Import each apps/<name>/backend/router.py and mount its `router`.

    Importing the module also runs its register_schema() /
    register_permissions() calls, which init_db() applies on startup."""
    for router_file in sorted(APPS_DIR.glob("*/backend/router.py")):
        app_name = router_file.parents[1].name
        spec = importlib.util.spec_from_file_location(f"portal_app_{app_name}", router_file)
        if spec is None or spec.loader is None:
            continue
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, "router"):
            app.include_router(mod.router)


_mount_generated_apps()


@app.get("/api/health")
def health():
    return {"status": "ok"}
