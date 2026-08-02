from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.routes import admin, auth, incidents, properties, providers
from app.api.routes.providers import seed_providers
from app.config import get_settings
from app.db import SessionLocal
from app.models import Provider

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Migrations own schema creation. Seeding is idempotent and only adds known provider metadata.
    with SessionLocal() as db:
        if db.get(Provider, "fixture.sarasota.dispatch") is None:
            seed_providers(db)
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
)


@app.middleware("http")
async def security_and_request_id(request: Request, call_next):
    rid = request.headers.get("X-Request-ID", str(uuid4()))
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.get("/healthz", tags=["system"])
def healthz() -> dict[str, object]:
    return {
        "status": "ok",
        "service": settings.app_name,
        "live_polling_enabled": settings.enable_live_sarasota_dispatch_polling,
        "phase": "4-property-resolution",
    }


@app.get("/readyz", tags=["system"])
def readyz() -> JSONResponse:
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception as exc:
        return JSONResponse(status_code=503, content={"status": "not_ready", "detail": str(exc)})
    return JSONResponse(status_code=200, content={"status": "ready"})


app.include_router(auth.router)
app.include_router(providers.router)
app.include_router(providers.retrieval_router)
app.include_router(incidents.router)
app.include_router(properties.import_router)
app.include_router(properties.match_router)
app.include_router(admin.router)
