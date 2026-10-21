from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import init_db, get_db
from .routers import auth, core, me
from .seed import seed


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with get_db() as conn:
        seed(conn)
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

app.include_router(auth.router)
app.include_router(me.router)
app.include_router(core.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
