from __future__ import annotations

import asyncio
import re
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from sqlalchemy import text
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.routes import (
    admin,
    auth,
    incidents,
    learning,
    opportunities,
    outcomes,
    properties,
    providers,
    workflow,
)
from app.api.routes.providers import seed_providers
from app.config import get_settings
from app.db import SessionLocal
from app.observability import configure_logging, log_request, metrics, monotonic_ms, prometheus_text
from app.providers.polling import SarasotaPollingService, SarasotaPollingWorker
from app.rate_limit import RateLimitExceeded, client_key, limiter

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging(get_settings().log_level)
    # Migrations own schema creation. Seeding is idempotent and only adds known provider metadata.
    with SessionLocal() as db:
        seed_providers(db)
        db.commit()
    polling_task = None
    current_settings = get_settings()
    if (
        current_settings.enable_live_sarasota_dispatch_polling
        and current_settings.enable_sarasota_polling_worker
    ):
        polling_task = asyncio.create_task(
            SarasotaPollingWorker(SarasotaPollingService(current_settings)).run()
        )
    try:
        yield
    finally:
        if polling_task is not None:
            polling_task.cancel()
            try:
                await polling_task
            except asyncio.CancelledError:
                pass


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/docs" if settings.enable_api_docs else None,
    redoc_url="/redoc" if settings.enable_api_docs else None,
    openapi_url="/openapi.json" if settings.enable_api_docs else None,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.web_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hostnames())


def _apply_security_headers(response: Response, *, path: str, request_id: str) -> Response:
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), geolocation=(), microphone=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    )
    if path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    if get_settings().app_env.lower() in {"production", "staging"}:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.middleware("http")
async def security_and_request_id(request: Request, call_next):
    current_settings = get_settings()
    supplied_rid = request.headers.get("X-Request-ID", "")
    rid = supplied_rid if re.fullmatch(r"[A-Za-z0-9._:-]{1,64}", supplied_rid) else str(uuid4())
    request.state.request_id = rid
    content_length = request.headers.get("content-length")
    if (
        content_length
        and content_length.isdigit()
        and int(content_length) > current_settings.max_request_bytes
    ):
        response = JSONResponse(
            status_code=413, content={"detail": "request exceeds configured size limit"}
        )
        response.headers["Retry-After"] = "0"
        return _apply_security_headers(response, path=request.url.path, request_id=rid)

    path = request.url.path
    limit = None
    scope = ""
    if request.method == "POST":
        if path in {"/api/v1/auth/login", "/api/v1/auth/bootstrap"}:
            limit = current_settings.rate_limit_login_requests
            scope = "auth"
        elif (
            path.endswith("/snapshots")
            or path.endswith("/imports")
            or path.endswith("/clients/import")
        ):
            limit = current_settings.rate_limit_upload_requests
            scope = "upload"
    if limit is not None:
        try:
            limiter.check(
                scope=scope,
                key=client_key(request.client.host if request.client else None),
                limit=limit,
                settings=current_settings,
            )
        except RateLimitExceeded as exc:
            response = JSONResponse(status_code=429, content={"detail": str(exc)})
            response.headers["Retry-After"] = str(exc.retry_after)
            return _apply_security_headers(response, path=path, request_id=rid)
        except Exception:
            if current_settings.app_env.lower() in {"production", "staging"}:
                response = JSONResponse(
                    status_code=503, content={"detail": "rate-limit service unavailable"}
                )
                return _apply_security_headers(response, path=path, request_id=rid)

    started = monotonic_ms()
    try:
        response = await call_next(request)
    except Exception:
        route_path = getattr(request.scope.get("route"), "path", path)
        duration = monotonic_ms() - started
        metrics.observe(request.method, route_path, 500, duration)
        log_request(
            method=request.method,
            path=route_path,
            status_code=500,
            duration_ms=duration,
            request_id=rid,
        )
        raise
    duration = monotonic_ms() - started
    route_path = getattr(request.scope.get("route"), "path", path)
    metrics.observe(request.method, route_path, response.status_code, duration)
    log_request(
        method=request.method,
        path=route_path,
        status_code=response.status_code,
        duration_ms=duration,
        request_id=rid,
    )
    return _apply_security_headers(response, path=path, request_id=rid)


@app.get("/healthz", tags=["system"])
def healthz() -> dict[str, object]:
    current_settings = get_settings()
    return {
        "status": "ok",
        "service": current_settings.app_name,
        "environment": current_settings.app_env,
        "live_polling_enabled": current_settings.enable_live_sarasota_dispatch_polling,
        "live_polling_worker_enabled": current_settings.enable_sarasota_polling_worker,
        "live_polling_interval_seconds": current_settings.sarasota_poll_interval_seconds,
        "learned_model_serving_enabled": current_settings.enable_learned_model_serving,
        "phase": "10-production-hardening",
    }


@app.get("/readyz", tags=["system"])
def readyz() -> JSONResponse:
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        current_settings = get_settings()
        if current_settings.redis_required_for_readiness:
            try:
                import redis  # type: ignore[import-not-found]

                redis.Redis.from_url(current_settings.redis_url, socket_connect_timeout=1).ping()
            except Exception as exc:
                return JSONResponse(
                    status_code=503,
                    content={"status": "not_ready", "dependency": "redis", "detail": str(exc)},
                )
    except Exception as exc:
        return JSONResponse(status_code=503, content={"status": "not_ready", "detail": str(exc)})
    return JSONResponse(status_code=200, content={"status": "ready"})


@app.get("/metrics", include_in_schema=False)
def metrics_endpoint() -> PlainTextResponse:
    return PlainTextResponse(prometheus_text(), media_type="text/plain; version=0.0.4")


app.include_router(auth.router)
app.include_router(providers.router)
app.include_router(providers.retrieval_router)
app.include_router(incidents.router)
app.include_router(properties.import_router)
app.include_router(properties.match_router)
app.include_router(opportunities.router)
app.include_router(workflow.router)
app.include_router(outcomes.router)
app.include_router(learning.router)
app.include_router(admin.router)
