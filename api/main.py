from __future__ import annotations

import itertools
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import ORJSONResponse, JSONResponse

# Add parent directory to path for shared module import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import (
    setup_logging,
    get_logger,
    api_rate_limiter,
)
from shared.logging_config import set_request_id
from shared.config import CORS_ORIGINS

from . import chat
from .routers import system, records, summary, notifications

# Backward-compatible re-exports — tests/test_input_validation.py imports
# these names directly from api.main.
from ._http_helpers import (  # noqa: F401
    _normalize_date,
    _validate_date_range,
    _validate_length,
)


# ==========================================================
# Logging Setup
# ==========================================================
setup_logging()
logger = get_logger(__name__)

# ==========================================================
# FastAPI App (v7: ORJSONResponse + GZip + CORS)
# ==========================================================
app = FastAPI(
    title="Production Data API",
    default_response_class=ORJSONResponse,  # Faster JSON serialization
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
# Middleware for Request ID and Rate Limiting
# ==========================================================
# GIL-safe counter for periodic rate-limiter cleanup (no lock needed)
_request_counter = itertools.count()
_CLEANUP_INTERVAL = 100


@app.middleware("http")
async def add_request_id_and_rate_limit(request, call_next):
    """Add request ID and apply rate limiting to API endpoints."""
    request_id = set_request_id()

    # Skip rate limiting for health checks
    if request.url.path in ["/", "/healthz", "/healthz/ai", "/docs", "/openapi.json"]:
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
