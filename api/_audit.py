# api/_audit.py
"""
Production Data Hub - Access Audit Log (auth-audit-v1)

Structured audit logging for authentication decisions. Each authenticated
request (grant or deny) emits one line on the dedicated ``audit`` logger,
carrying request_id, client IP, method, path, masked principal and outcome.

Secrets are never logged: the ``principal`` field comes from
:func:`shared.auth.mask_secret` (only the last 4 chars are revealed).
"""

from __future__ import annotations

from shared import AuthResult
from shared.logging_config import get_logger

audit_logger = get_logger("audit")


def record_auth_event(
    *,
    request_id: str | None,
    client_ip: str,
    method: str,
    path: str,
    result: AuthResult,
    status_code: int,
) -> None:
    """Emit one structured audit line for an authentication decision.

    No-op when auth is disabled (``reason == "auth_disabled"``) so that the
    default open-access configuration produces no extra log noise.
    """
    if result.reason == "auth_disabled":
        return

    outcome = "GRANT" if result.authenticated else "DENY"
    audit_logger.info(
        "[AUDIT] %s | rid=%s ip=%s %s %s | principal=%s method=%s reason=%s status=%s",
        outcome,
        request_id or "-",
        client_ip,
        method,
        path,
        result.principal or "-",
        result.method or "-",
        result.reason or "-",
        status_code,
    )
