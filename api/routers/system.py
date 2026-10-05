"""System endpoints: root, metrics, health.

Moved from api/main.py during api-router-split (2026-05-22). Bodies are
1:1 with the originals — only the decorator binding changes (app.get -> router.get)
and module-level state moves with the routes that own it.
"""
from __future__ import annotations

import datetime as dt
import os
import sqlite3

from fastapi import APIRouter, Response

from shared import (
    ARCHIVE_DB_FILE,
    DATABASE_DIR,
    DB_FILE,
    DBRouter,
    get_cache_stats,
    get_logger,
)
from shared.metrics import performance_monitor

from ..notifications.metrics import render_prometheus

logger = get_logger(__name__)
router = APIRouter()


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


@router.get(
    "/metrics",
    response_class=Response,
    responses={200: {"content": {"text/plain": {}}}},
)
def metrics_prometheus() -> Response:
    """Prometheus-compatible snapshot of webhook operational metrics."""
    return Response(
        content=render_prometheus(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@router.get("/healthz")
def health_check():
    """
    API health check endpoint (lightweight).
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

    # v7: API Cache stats
    status["cache"] = get_cache_stats()

    # Disk space check: statvfs on POSIX, shutil.disk_usage on Windows.
    # (Previously the shutil fallback sat in an `except` guarded by
    # `hasattr(os, 'statvfs')`, so on Windows it was dead code and
    # disk_free_gb was silently never set. Branch explicitly instead.)
    try:
        if hasattr(os, "statvfs"):
            disk_stat = os.statvfs(str(DATABASE_DIR))
            free_gb = (disk_stat.f_frsize * disk_stat.f_bavail) / (1024**3)
            status["disk_free_gb"] = round(free_gb, 2)
        else:
            import shutil
            free = shutil.disk_usage(str(DATABASE_DIR)).free
            status["disk_free_gb"] = round(free / (1024**3), 2)
    except (AttributeError, OSError, ValueError) as e:
        logger.debug("disk space check failed: %s", e)

    return status
