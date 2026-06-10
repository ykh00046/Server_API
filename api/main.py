from __future__ import annotations

import itertools
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, ORJSONResponse

# Add parent directory to path for shared module import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import (
    api_rate_limiter,
    authenticate,
    get_logger,
    is_public_path,
    load_auth_settings,
    setup_logging,
)
from shared.config import (
    API_AUTH_ENABLED,
    API_BEARER_TOKENS,
    API_KEYS,
    CORS_ORIGINS,
    WEBHOOK_WORKER_ENABLED,
)
from shared.logging_config import get_request_id, set_request_id

from . import chat
from ._audit import record_auth_event

# Backward-compatible re-exports — tests/test_input_validation.py imports
# these names directly from api.main.
from ._http_helpers import (  # noqa: F401
    _normalize_date,
    _validate_date_range,
    _validate_length,
)
from .notifications.worker import WebhookDispatchWorker
from .routers import notifications, records, summary, system

# ==========================================================
# Logging Setup
# ==========================================================
setup_logging()
logger = get_logger(__name__)

# auth-audit-v1: surface a misconfiguration where auth is enabled but no
# credentials are configured — every protected route would 401 (fail-closed).
if API_AUTH_ENABLED and not (API_KEYS or API_BEARER_TOKENS):
    logger.warning(
        "[Auth] API_AUTH_ENABLED=true but no API_KEYS/API_BEARER_TOKENS set "
        "— all protected routes will return 401."
    )

_webhook_worker = WebhookDispatchWorker()  # webhook-async-dispatch-v2

@asynccontextmanager
async def _lifespan(app: FastAPI):
    if WEBHOOK_WORKER_ENABLED: _webhook_worker.start()
    try: yield
    finally: _webhook_worker.stop()

# ==========================================================
# FastAPI App (v7: ORJSONResponse + GZip + CORS)
# ==========================================================
app = FastAPI(
    title="Production Data API",
    default_response_class=ORJSONResponse,  # Faster JSON serialization
    lifespan=_lifespan,
)
app.add_middleware(GZipMiddleware, minimum_size=500)  # Compress responses > 500 bytes

# CORS — allows future web frontend (React/Next.js) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Domain routers (api-router-split, 2026-05-22) — chat first to preserve
# include order from the pre-split layout.
app.include_router(chat.router)
app.include_router(system.router)
app.include_router(records.router)
app.include_router(summary.router)
app.include_router(notifications.router)


# ==========================================================
# Authentication + Audit Middleware (auth-audit-v1)
# ==========================================================
# Registered BEFORE add_request_id_and_rate_limit on purpose: Starlette runs
# the most-recently-added middleware outermost, so the request_id/rate-limit
# middleware stays outermost (request_id is set first) and this auth layer runs
# inner — it can therefore reference get_request_id() in audit logs.
# When API_AUTH_ENABLED is False (default) this is a single-branch pass-through,
# preserving the existing open-access behavior and the full test suite.
@app.middleware("http")
async def auth_and_audit(request, call_next):
    """Authenticate protected routes and emit an audit log per decision."""
    settings = load_auth_settings()

    # Pass-through when disabled, for CORS preflight (carries no credentials by
    # spec), and for public paths (single source of truth in shared.auth).
    if (
        not settings.enabled
        or request.method == "OPTIONS"
        or is_public_path(request.url.path)
    ):
        return await call_next(request)

    result = authenticate(request.headers, settings)
    request_id = get_request_id()
    client_ip = request.client.host if request.client else "unknown"

    if not result.authenticated:
        record_auth_event(
            request_id=request_id,
            client_ip=client_ip,
            method=request.method,
            path=request.url.path,
            result=result,
            status_code=401,
        )
        return JSONResponse(
            status_code=401,
            content={"detail": "Unauthorized"},
            headers={
                "WWW-Authenticate": "Bearer",
                "X-Request-ID": request_id or "",
            },
        )

    record_auth_event(
        request_id=request_id,
        client_ip=client_ip,
        method=request.method,
        path=request.url.path,
        result=result,
        status_code=200,
    )
    return await call_next(request)


# ==========================================================
# Middleware for Request ID and Rate Limiting
# ==========================================================
# GIL-safe counter for periodic rate-limiter cleanup (no lock needed)
_request_counter = itertools.count()
_CLEANUP_INTERVAL = 100


@app.middleware("http")
async def add_request_id_and_rate_limit(request, call_next):
    """Add request ID and apply rate limiting to API endpoints."""
    request_id = set_request_id()

    # Skip rate limiting for public paths — shared.auth.PUBLIC_PATHS is the
    # single source of truth (same exemption set as the auth middleware).
    if is_public_path(request.url.path):
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    # Apply rate limiting to API endpoints (except /chat which has its own limiter)
    if request.url.path.startswith("/chat"):
        # Chat has its own rate limiter in the endpoint
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    # General API rate limiting
    client_ip = request.client.host if request.client else "unknown"
    if not api_rate_limiter.is_allowed(client_ip):
        retry_after = api_rate_limiter.retry_after(client_ip)
        logger.warning(
            f"[Rate Limited] ip={client_ip} | path={request.url.path} | "
            f"retry_after={retry_after}s"
        )
        return JSONResponse(
            status_code=429,
            content={"detail": f"Rate limit exceeded. Try again in {retry_after} seconds."},
            headers={
                "Retry-After": str(retry_after),
                "X-Request-ID": request_id,
                "X-RateLimit-Limit": "60",
                "X-RateLimit-Remaining": "0",
            }
        )

    # Add rate limit headers to response
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-RateLimit-Limit"] = "60"
    response.headers["X-RateLimit-Remaining"] = str(api_rate_limiter.remaining(client_ip))

    # Periodic cleanup (every 100 requests — no lock needed with itertools.count)
    should_cleanup = next(_request_counter) % _CLEANUP_INTERVAL == 0

    if should_cleanup:
        removed = api_rate_limiter.cleanup()
        if removed > 0:
            logger.debug(f"[Rate Limiter Cleanup] Removed {removed} expired IPs")

    return response
