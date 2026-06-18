# shared/config.py
"""
Production Data Hub - Configuration Constants

All hardcoded values are centralized here for maintainability.
Environment variables can override default values.
"""

import logging
import os
import sys
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
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash-lite")
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
# SSE Streaming Configuration
# ==========================================================
STREAM_HEARTBEAT_SEC = float(os.getenv("STREAM_HEARTBEAT_SEC", 10.0))
STREAM_TIMEOUT_SEC = float(os.getenv("STREAM_TIMEOUT_SEC", 120.0))
STREAM_BUFFER_FLUSH_MS = float(os.getenv("STREAM_BUFFER_FLUSH_MS", 50.0))

# ==========================================================
# CORS
# ==========================================================
_DEFAULT_CORS_ORIGINS = (
    "http://localhost:3000,"
    "http://localhost:5173,"
    "http://localhost:8502,"
    "http://192.168.200.107:8502,"
    "http://192.168.200.107:3000"
)
CORS_ORIGINS: list[str] = [
    o.strip() for o in os.getenv("CORS_ORIGINS", _DEFAULT_CORS_ORIGINS).split(",") if o.strip()
]

# ==========================================================
# Custom Query Safety (security-and-test-improvement)
# ==========================================================
CUSTOM_QUERY_TIMEOUT_SEC = float(os.getenv("CUSTOM_QUERY_TIMEOUT_SEC", 10.0))

# ==========================================================
# API Authentication (auth-audit-v1) — opt-in, default OFF
# ==========================================================
# When False (default), the auth middleware is a pass-through so existing
# open-access behavior and the whole test suite are preserved unchanged.
# Enable in production via .env: API_AUTH_ENABLED=true + API_KEYS / API_BEARER_TOKENS.
_TRUTHY = {"1", "true", "yes", "on"}
API_AUTH_ENABLED = os.getenv("API_AUTH_ENABLED", "false").strip().lower() in _TRUTHY
API_KEYS: list[str] = [
    k.strip() for k in os.getenv("API_KEYS", "").split(",") if k.strip()
]
API_BEARER_TOKENS: list[str] = [
    t.strip() for t in os.getenv("API_BEARER_TOKENS", "").split(",") if t.strip()
]

# ==========================================================
# Webhook Notifications (webhook-notifications-v1)
# ==========================================================
NOTIFICATIONS_DB_FILE = DATABASE_DIR / "notifications.db"
WEBHOOK_TIMEOUT_SEC = float(os.getenv("WEBHOOK_TIMEOUT_SEC", 5.0))
WEBHOOK_USER_AGENT = os.getenv("WEBHOOK_USER_AGENT", "Server_API-Webhook/1.0")
WEBHOOK_MAX_PAYLOAD_BYTES = int(os.getenv("WEBHOOK_MAX_PAYLOAD_BYTES", 65536))

# ==========================================================
# Material Requests intake (materials-api-v1)
# ==========================================================
# Separate DB file (materials.db) keeps webcloring-pdf 자재요청 backup data out
# of production_analysis.db (ERP-rewritten) and notifications.db. Replaces the
# prior Google Sheets backup target — see webcloring-pdf ApiBackupManager.
MATERIALS_DB_FILE = DATABASE_DIR / "materials.db"

# Manual automation trigger (materials-run-v1): the dashboard "지금 실행" button
# spawns the webcloring-pdf 포털 자동화 (`main.py --auto`) on the SAME ops PC.
# Disabled by default — spawning a process from a web request is opt-in.
MATERIALS_RUN_ENABLED = os.getenv("MATERIALS_RUN_ENABLED", "0") not in {
    "0", "false", "False", "no", "off", ""
}
# webcloring-pdf 디렉토리(기본: repo의 submodule)와 실행 파이썬(기본: 현재 인터프리터).
MATERIALS_BOT_DIR = Path(os.getenv("MATERIALS_BOT_DIR", str(BASE_DIR / "webcloring-pdf")))
MATERIALS_BOT_PYTHON = os.getenv("MATERIALS_BOT_PYTHON", sys.executable)

# ==========================================================
# Webhook Async Dispatch (webhook-async-dispatch-v2)
# ==========================================================
WEBHOOK_MAX_ATTEMPTS = int(os.getenv("WEBHOOK_MAX_ATTEMPTS", 5))
WEBHOOK_WORKER_TICK_SEC = float(os.getenv("WEBHOOK_WORKER_TICK_SEC", 0.5))
WEBHOOK_WORKER_BATCH = int(os.getenv("WEBHOOK_WORKER_BATCH", 16))
WEBHOOK_WORKER_ENABLED = os.getenv("WEBHOOK_WORKER_ENABLED", "1") not in {
    "0", "false", "False", "no", "off"
}


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

# ==========================================================
# Anomaly Detection (anomaly-detection-v1)
# ==========================================================
# 생산 데이터를 주기 스캔해 급감/급증/장시간 미생산을 규칙 기반으로 탐지하고,
# 신규 이상만 기존 webhook emit_event 로 비동기 발행한다. 스캔은 read-only.
ANOMALY_ENABLED = os.getenv("ANOMALY_ENABLED", "1") not in {
    "0", "false", "False", "no", "off", ""
}
# 후행 평균 기준선 산출에 사용할 일수(직전 완료일 제외, 그 이전 N일).
ANOMALY_BASELINE_DAYS = int(os.getenv("ANOMALY_BASELINE_DAYS", 14))
# 후행 평균 대비 하락/상승 비율(%) 임계치. 경계값(>=)에서 발동.
ANOMALY_DROP_PCT = float(os.getenv("ANOMALY_DROP_PCT", 50.0))
ANOMALY_SPIKE_PCT = float(os.getenv("ANOMALY_SPIKE_PCT", 100.0))
# 활성 품목이 이 일수 이상 미생산이면 stale 로 판정.
ANOMALY_STALE_DAYS = int(os.getenv("ANOMALY_STALE_DAYS", 7))
# 기준선이 이 값 미만이면 급감/급증 판정을 건너뛴다(0 나눗셈·노이즈 방지).
ANOMALY_MIN_BASELINE_QTY = float(os.getenv("ANOMALY_MIN_BASELINE_QTY", 1.0))
# 동일 이상(key) 재발행 억제 쿨다운(초). 기본 24시간.
ANOMALY_COOLDOWN_SEC = int(os.getenv("ANOMALY_COOLDOWN_SEC", 86400))
# 스케줄 러너 데몬 기본 주기(초). 기본 1시간.
ANOMALY_SCAN_INTERVAL_SEC = int(os.getenv("ANOMALY_SCAN_INTERVAL_SEC", 3600))
# 쿨다운/마지막 스캔 시각을 저장하는 상태파일.
ANOMALY_STATE_FILE = DATABASE_DIR / ".anomaly_state.json"
