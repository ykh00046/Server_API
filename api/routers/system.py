"""System endpoints: root, metrics, health.

Moved from api/main.py during api-router-split (2026-05-22). Bodies are
1:1 with the originals — only the decorator binding changes (app.get -> router.get)
and module-level state moves with the routes that own it.
"""
from __future__ import annotations

import datetime as dt
import os
import sqlite3
import threading
import time

from fastapi import APIRouter

from shared import (
    ARCHIVE_DB_FILE,
    DATABASE_DIR,
    DB_FILE,
    DBRouter,
    get_cache_stats,
    get_logger,
)
from shared.metrics import performance_monitor

from .. import _session_store as _sstore

logger = get_logger(__name__)
router = APIRouter()


# ==========================================================
# AI Health Check Cache - Thread-safe
# ==========================================================
_ai_health_cache = {
    "status": "unknown",
    "last_check": 0,
    "message": "Not checked yet"
}
_ai_health_cache_lock = threading.Lock()
AI_HEALTH_CACHE_TTL = 600  # 10 minutes


@router.get("/")
def read_root():
    return {"status": "active", "system": "Production Data Hub API"}


@router.get("/metrics/performance")
def metrics_performance():
    """Rolling-window query performance metrics (count / avg / p50 / p95 / p99 / cache_hit_rate)."""
    return performance_monitor.get_all_stats()


@router.get("/metrics/cache")
def metrics_cache():
    """Combined cache + performance snapshot for monitoring."""
    return {
        "api_cache": get_cache_stats(),
        "performance": performance_monitor.get_all_stats(),
    }


@router.get("/healthz")
def health_check():
    """
    API health check endpoint (lightweight).
    AI check uses cached status - call /healthz/ai for fresh check.
    """
    status = {
        "status": "ok",
        "timestamp": dt.datetime.now().isoformat(),
    }

    # Database check
    try:
        with DBRouter.get_connection(use_archive=False) as conn:
            conn.execute("SELECT 1").fetchone()
        status["database"] = "connected"

        if DB_FILE.exists():
            status["db_size_mb"] = round(DB_FILE.stat().st_size / (1024 * 1024), 2)
    except (sqlite3.Error, OSError) as e:
        status["status"] = "degraded"
        status["database"] = f"error: {e}"

    # Archive DB check
    if ARCHIVE_DB_FILE.exists():
        status["archive_db"] = "available"
        status["archive_size_mb"] = round(ARCHIVE_DB_FILE.stat().st_size / (1024 * 1024), 2)
    else:
        status["archive_db"] = "not_found"

    # AI API check (cached, lightweight)
    api_key_exists = bool(os.getenv("GEMINI_API_KEY"))
    status["ai_api"] = {
        "key_configured": api_key_exists,
        "cached_status": _ai_health_cache["status"],
        "last_check_age_sec": (
            int(time.time() - _ai_health_cache["last_check"])
            if _ai_health_cache["last_check"] > 0 else None
        ),
    }

    # v7: API Cache stats
    status["cache"] = get_cache_stats()

    # Disk space check
    try:
        disk_stat = os.statvfs(str(DATABASE_DIR)) if hasattr(os, 'statvfs') else None
        if disk_stat:
            free_gb = (disk_stat.f_frsize * disk_stat.f_bavail) / (1024**3)
            status["disk_free_gb"] = round(free_gb, 2)
    except (AttributeError, OSError):
        # Windows doesn't have statvfs, use shutil
        try:
            import shutil
            total, used, free = shutil.disk_usage(str(DATABASE_DIR))
            status["disk_free_gb"] = round(free / (1024**3), 2)
        except (OSError, ValueError) as e:
            logger.debug("disk_usage fallback failed: %s", e)

    return status


@router.get("/healthz/ai")
async def ai_health_check():
    """
    AI API health check with actual ping (cached for 10 minutes).
    Use this sparingly to avoid quota consumption.
    """
    with _ai_health_cache_lock:
        cache_age = time.time() - _ai_health_cache["last_check"]
        if cache_age < AI_HEALTH_CACHE_TTL and _ai_health_cache["status"] != "unknown":
            return {
                "status": _ai_health_cache["status"],
                "message": _ai_health_cache["message"],
                "cached": True,
                "cache_age_sec": int(cache_age),
                "cache_ttl_sec": AI_HEALTH_CACHE_TTL,
                "sessions": _sstore.stats(),
            }

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        with _ai_health_cache_lock:
            _ai_health_cache.update({
                "status": "error",
                "last_check": time.time(),
                "message": "API key not configured"
            })
        return {
            "status": "error",
            "message": "GEMINI_API_KEY not configured",
            "cached": False,
            "sessions": _sstore.stats(),
        }

    try:
        from google import genai
        from google.genai.errors import ClientError, ServerError

        client = genai.Client(api_key=api_key)

        models = client.models.list()
        model_count = sum(1 for _ in models)

        with _ai_health_cache_lock:
            _ai_health_cache.update({
                "status": "ok",
                "last_check": time.time(),
                "message": f"Connected, {model_count} models available"
            })

        return {
            "status": "ok",
            "message": _ai_health_cache["message"],
            "cached": False,
            "sessions": _sstore.stats(),
        }

    except ClientError as e:
        error_msg = f"Client error: {e}"
        status = "error"
        if "429" in str(e):
            error_msg = "Rate limited (quota may be exhausted)"
            status = "rate_limited"

        with _ai_health_cache_lock:
            _ai_health_cache.update({
                "status": status,
                "last_check": time.time(),
                "message": error_msg
            })

        return {
            "status": status,
            "message": error_msg,
            "cached": False,
            "sessions": _sstore.stats(),
        }

    except ServerError as e:
        with _ai_health_cache_lock:
            _ai_health_cache.update({
                "status": "degraded",
                "last_check": time.time(),
                "message": f"Server error: {e}"
            })
        return {
            "status": "degraded",
            "message": str(e),
            "cached": False,
            "sessions": _sstore.stats(),
        }

    except Exception as e:  # noqa: BLE001 — health 캐시는 어떤 외부 호출 오류에서도 degraded/error 상태를 기록해야 한다
        with _ai_health_cache_lock:
            _ai_health_cache.update({
                "status": "error",
                "last_check": time.time(),
                "message": str(e)
            })
        return {
            "status": "error",
            "message": str(e),
            "cached": False,
            "sessions": _sstore.stats(),
        }
