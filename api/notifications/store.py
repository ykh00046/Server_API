"""SQLite repository facade for webhooks and delivery history.

A separate DB file (notifications.db) keeps webhook metadata out of the
production_analysis.db that the ERP intake pipeline rewrites periodically.

This module is now a thin **back-compat facade**. Connection management,
schema migration, dataclasses, and CRUD operations were split out during
the 2026-05-27 structure-cleanup:

    _store_connection.py  — _local, _get_conn, _ensure_schema*, reset_for_tests
    _store_models.py      — WebhookRecord, ClaimedDelivery, _row_to_*, _now_iso
    webhooks_repo.py      — create/get/list/update/delete_webhook
    deliveries_repo.py    — create_pending/finalize/enqueue/claim/record_attempt/
                            queue_stats/requeue/list_deliveries/get_delivery

External callers should keep importing from ``api.notifications.store``;
new internal code may import from the sub-modules directly.
"""
from __future__ import annotations

from ._store_connection import (  # noqa: F401
    _ensure_schema,
    _ensure_schema_v2,
    _get_conn,
    _local,
    reset_for_tests,
)
from ._store_models import (  # noqa: F401
    ClaimedDelivery,
    WebhookRecord,
    _generate_secret,
    _now_iso,
    _record_to_public,
    _row_to_delivery,
    _row_to_record,
)
from .webhooks_repo import (  # noqa: F401
    create_webhook,
    delete_webhook,
    get_public,
    get_record,
    list_public,
    list_records,
    update_webhook,
)
from .deliveries_repo import (  # noqa: F401
    RETRYABLE_TERMINAL_STATUSES,
    claim_due_deliveries,
    create_pending_delivery,
    enqueue_delivery,
    finalize_delivery,
    get_delivery,
    list_deliveries,
    list_retryable_delivery_ids,
    queue_stats,
    record_attempt,
    requeue_deliveries,
    requeue_delivery,
)

__all__ = [
    "ClaimedDelivery",
    "RETRYABLE_TERMINAL_STATUSES",
    "WebhookRecord",
    "claim_due_deliveries",
    "create_pending_delivery",
    "create_webhook",
    "delete_webhook",
    "enqueue_delivery",
    "finalize_delivery",
    "get_delivery",
    "get_public",
    "get_record",
    "list_deliveries",
    "list_public",
    "list_records",
    "list_retryable_delivery_ids",
    "queue_stats",
    "record_attempt",
    "requeue_deliveries",
    "requeue_delivery",
    "reset_for_tests",
    "update_webhook",
]
