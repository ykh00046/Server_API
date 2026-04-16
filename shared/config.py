# shared/config.py
"""
Production Data Hub - Configuration Constants

All hardcoded values are centralized here for maintainability.
Environment variables can override default values.
"""

import logging
import os
from pathlib import Path
from dotenv import load_dotenv

_logger = logging.getLogger(__name__)

# Load .env file
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ==========================================================
# Paths
# ==========================================================
BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_DIR = BASE_DIR / "database"
LOGS_DIR = BASE_DIR / "logs"

DB_FILE = DATABASE_DIR / "production_analysis.db"
ARCHIVE_DB_FILE = DATABASE_DIR / "archive_2025.db"

# ==========================================================
# Archive Policy
# ==========================================================
# Archive DB contains data BEFORE this year (i.e., 2025 and earlier)
# Live DB contains data FROM this year onwards (i.e., 2026+)
ARCHIVE_CUTOFF_YEAR = 2026
ARCHIVE_CUTOFF_DATE = f"{ARCHIVE_CUTOFF_YEAR}-01-01"

# ==========================================================
# Server Ports (can be overridden via .env)
# ==========================================================
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", 8502))
API_PORT = int(os.getenv("API_PORT", 8000))
API_BASE_URL = os.getenv("API_BASE_URL", f"http://localhost:{API_PORT}")

# ==========================================================
# Database Connection
# ==========================================================
DB_TIMEOUT = 10.0  # seconds
SLOW_QUERY_THRESHOLD_MS = 500  # Log WARNING for queries exceeding this

# ==========================================================
# AI / Gemini
# ==========================================================
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.1-flash-lite")
GEMINI_FALLBACK_ENABLED = os.getenv("GEMINI_FALLBACK_ENABLED", "true").lower() == "true"

# ==========================================================
# Logging
# ==========================================================
LOG_FILE = LOGS_DIR / "app.log"
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
LOG_BACKUP_COUNT = 5
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ==========================================================
# Date Handling Policy (6.4)
# ==========================================================
# - SQL filters operate on Day-level only
# - Monthly aggregation uses substr(production_date, 1, 7)
# - API input date_from/date_to normalized to 'YYYY-MM-DD'
DATE_FORMAT = "%Y-%m-%d"

# ==========================================================
# Rate Limiting Configuration
# ==========================================================
# Chat endpoint is more restrictive due to AI API costs
RATE_LIMIT_CHAT = 20      # requests per minute
RATE_LIMIT_API = 60       # requests per minute (general API)
RATE_LIMIT_WINDOW = 60    # seconds

# ==========================================================
# Chat Session Store (security-and-test-improvement)
# ==========================================================
CHAT_SESSION_TTL_SEC = int(os.getenv("CHAT_SESSION_TTL_SEC", 1800))
CHAT_SESSION_MAX_PER_IP = int(os.getenv("CHAT_SESSION_MAX_PER_IP", 20))
CHAT_SESSION_MAX_TOTAL = int(os.getenv("CHAT_SESSION_MAX_TOTAL", 1000))

# ==========================================================
# Custom Query Safety (security-and-test-improvement)
# ==========================================================
CUSTOM_QUERY_TIMEOUT_SEC = float(os.getenv("CUSTOM_QUERY_TIMEOUT_SEC", 10.0))


def _load_archive_whitelist() -> tuple[Path, ...]:
    raw = os.getenv("ARCHIVE_DB_WHITELIST", "").strip()
    if not raw:
        return (ARCHIVE_DB_FILE.resolve(),)
    items: list[Path] = []
    for part in raw.split(";"):
        p = part.strip()
        if not p:
            continue
        resolved = Path(p).resolve()
        if not resolved.exists():
            _logger.warning(
                "ARCHIVE_DB_WHITELIST entry not found at import: %s", resolved
            )
        items.append(resolved)
    return tuple(items) if items else (ARCHIVE_DB_FILE.resolve(),)


ARCHIVE_DB_WHITELIST: tuple[Path, ...] = _load_archive_whitelist()
