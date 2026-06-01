# shared/logging_config.py
"""
Production Data Hub - Centralized Logging Configuration

Features (Section 6.6):
- RotatingFileHandler for log file size/count limits
- Common log fields: request_id, db_targets, sql_kind, duration_ms, row_count
- Consistent format across all modules
"""

from __future__ import annotations

import logging
import sys
import time
import uuid
from logging.handlers import RotatingFileHandler
from contextvars import ContextVar
from typing import Any

from .config import (
    LOGS_DIR,
    LOG_FILE,
    LOG_MAX_BYTES,
    LOG_BACKUP_COUNT,
    LOG_DATE_FORMAT,
    SLOW_QUERY_THRESHOLD_MS,
)

# Context variable for request tracking
_request_id: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    """Get current request ID from context"""
    return _request_id.get()


def set_request_id(request_id: str | None = None) -> str:
    """
    Set request ID for current context.
    If None, generates a new UUID.
    Returns the request_id that was set.
    """
    rid = request_id or str(uuid.uuid4())[:8]
    _request_id.set(rid)
    return rid


class RequestIdFilter(logging.Filter):
    """Add request_id to all log records"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


def setup_logging(level: int = logging.INFO) -> None:
    """
    Initialize logging configuration for the application.

    Call this once at application startup (e.g., in main.py or manager.py).

    Args:
        level: Logging level (default INFO)
    """
    # Ensure logs directory exists
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # Custom format with request_id
    log_format = "%(asctime)s | %(levelname)-8s | %(request_id)s | %(name)s | %(message)s"

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear existing handlers
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter(log_format, LOG_DATE_FORMAT))
    console_handler.addFilter(RequestIdFilter())
    root_logger.addHandler(console_handler)

    # File handler with rotation
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8"
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(log_format, LOG_DATE_FORMAT))
    file_handler.addFilter(RequestIdFilter())
    root_logger.addHandler(file_handler)

    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a module.

    Usage:
        logger = get_logger(__name__)
        logger.info("Message")
    """
    return logging.getLogger(name)


class QueryLogger:
    """
    Context manager for logging database queries with common fields.

    Usage:
        with QueryLogger("records", targets) as ql:
            result = DBRouter.query(sql, params)
            ql.set_row_count(len(result))
        # Automatically logs duration_ms and row_count on exit
    """

    def __init__(
        self,
        sql_kind: str,
        db_targets: Any = None,
        logger: logging.Logger | None = None
    ):
        """
        Args:
            sql_kind: Type of query (records, summary, search, etc.)
            db_targets: DBTargets instance or description string
            logger: Logger to use (default: module logger)
        """
        self.sql_kind = sql_kind
        self.db_targets = db_targets
        self.logger = logger or logging.getLogger(__name__)
        self.start_time: float = 0
        self.row_count: int | None = None
        self.extra_info: dict[str, Any] = {}

    def __enter__(self) -> "QueryLogger":
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        duration_ms = (time.perf_counter() - self.start_time) * 1000

        # Format db_targets for logging
        if hasattr(self.db_targets, "use_archive"):
            targets_str = f"archive={self.db_targets.use_archive},live={self.db_targets.use_live}"
        else:
            targets_str = str(self.db_targets) if self.db_targets else "-"

        # Build log message with common fields
        parts = [
            f"sql_kind={self.sql_kind}",
            f"db_targets=({targets_str})",
            f"duration_ms={duration_ms:.1f}",
        ]

        if self.row_count is not None:
            parts.append(f"row_count={self.row_count}")

        for key, value in self.extra_info.items():
            parts.append(f"{key}={value}")

        message = " | ".join(parts)

        if exc_type is not None:
            self.logger.error(f"[Query Failed] {message} | error={exc_val}")
        elif duration_ms >= SLOW_QUERY_THRESHOLD_MS:
            self.logger.warning(f"[Slow Query] {message}")
        else:
            self.logger.info(f"[Query OK] {message}")

    def set_row_count(self, count: int) -> None:
        """Set the row count for logging"""
        self.row_count = count

    def add_info(self, key: str, value: Any) -> None:
        """Add extra info to log output"""
        self.extra_info[key] = value
