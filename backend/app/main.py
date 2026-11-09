import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.bootstrap import ensure_bootstrap_admin
from app.db import SessionLocal
from app.routers import activity, auth, insight, media, operations, reports, signals, sites, tasks, users

log = logging.getLogger("namaa")


@asynccontextmanager
async def lifespan(_: FastAPI):
    with SessionLocal() as db:
        ensure_bootstrap_admin(db)
    yield


app = FastAPI(title="Namaa API", version="0.1.0", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(sites.router)
app.include_router(sites.districts_router)
app.include_router(operations.router)
app.include_router(signals.router)
app.include_router(tasks.router)
app.include_router(media.router)
app.include_router(insight.router)
app.include_router(reports.router)
app.include_router(activity.router)


@app.get("/api/health", tags=["health"])
def health():
    return {"status": "ok"}
