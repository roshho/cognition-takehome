import importlib
import importlib.machinery
import importlib.util
import os
import sys
import types
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from portal_platform.audit import RequestIdMiddleware
from portal_platform.db import run_seeds

from .db import init_db, get_db
from .routers import auth, core, me
from .seed import seed

# Apps (built-in and generated) live at <repo>/apps/<name>/backend/router.py (locally) or
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
        run_seeds(conn)
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


def _load_app(backend_dir: Path):
    """Import apps/<name>/backend as package ``portal_apps.<name>`` (so its
    modules can use relative imports) and return its ``router`` module."""
    pkg_name = "portal_apps." + backend_dir.parent.name.replace("-", "_")
    for k in [k for k in sys.modules if k == pkg_name or k.startswith(pkg_name + ".")]:
        del sys.modules[k]
    if "portal_apps" not in sys.modules:
        root = types.ModuleType("portal_apps")
        root.__path__ = []
        sys.modules["portal_apps"] = root
    spec = importlib.machinery.ModuleSpec(pkg_name, None, is_package=True)
    spec.submodule_search_locations = [str(backend_dir)]
    sys.modules[pkg_name] = importlib.util.module_from_spec(spec)
    return importlib.import_module(f"{pkg_name}.router")


def _mount_apps() -> None:
    """Mount every apps/<name>/backend/router.py's ``router``.

    Importing the module also runs its register_schema / register_seed /
    register_permissions / register_adapter / register_tool calls, which
    startup (init_db, run_seeds) and the core endpoints then use."""
    for router_file in sorted(APPS_DIR.glob("*/backend/router.py")):
        mod = _load_app(router_file.parent)
        if hasattr(mod, "router"):
            app.include_router(mod.router)


_mount_apps()


@app.get("/api/health")
def health():
    return {"status": "ok"}
