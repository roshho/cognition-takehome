from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from portal_platform.audit import RequestIdMiddleware

from .db import init_db, get_db
from .flags import seed_flags
from .kyc import seed_kyc
from .refunds import seed_refunds
from .routers import auth, core, flags as flags_router, kyc as kyc_router, me, refunds as refunds_router
from .seed import seed


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


@app.get("/api/health")
def health():
    return {"status": "ok"}
