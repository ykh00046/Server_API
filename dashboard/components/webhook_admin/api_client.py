"""HTTP client for the /notifications/* webhook admin endpoints.

Sole IO layer for the dashboard webhook admin page. All other modules
(formatters, views) must be pure / Streamlit-only and never call httpx
directly. The constructor accepts an injectable `transport` so tests can
plug in `httpx.MockTransport`.
"""
from __future__ import annotations

import json
from typing import Any

import httpx


class WebhookAdminError(Exception):
    """Normalized failure surface for the webhook admin client.

    `status is None` indicates a network/timeout failure (no HTTP exchange
    completed). `body` is the raw response text for diagnostics.
    """

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        body: str | None = None,
    ):
        super().__init__(message)
        self.status = status
        self.body = body


def _extract_detail(resp: httpx.Response) -> str:
    try:
        payload = resp.json()
    except (ValueError, json.JSONDecodeError):
        return resp.text[:200] or f"HTTP {resp.status_code}"
    if isinstance(payload, dict) and "detail" in payload:
        d = payload["detail"]
        return d if isinstance(d, str) else str(d)
    return resp.text[:200] or f"HTTP {resp.status_code}"


class WebhookAdminClient:
    """Thin wrapper over the /notifications/* routes.

    Reused per page render. Cheap to construct (lazy connection). The
    underlying httpx.Client is closed on `close()` / context manager exit;
    Streamlit reruns drop the reference so explicit cleanup is not required
    for the page lifecycle.
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> WebhookAdminClient:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Internal dispatch
    # ------------------------------------------------------------------
    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: Any | None = None,
        expect_json: bool = True,
    ) -> Any:
        try:
            resp = self._client.request(method, path, params=params, json=json)
        except httpx.TimeoutException as e:
            raise WebhookAdminError("request timed out", status=None, body=str(e)) from e
        except httpx.TransportError as e:
            raise WebhookAdminError(str(e), status=None, body=None) from e

        if resp.status_code >= 400:
            raise WebhookAdminError(
                _extract_detail(resp),
                status=resp.status_code,
                body=resp.text,
            )

        if not expect_json or resp.status_code == 204 or not resp.content:
            return None
        try:
            return resp.json()
        except (ValueError, json.JSONDecodeError) as e:
            raise WebhookAdminError(
                f"invalid JSON in 2xx response: {e}",
                status=resp.status_code,
                body=resp.text[:200],
            ) from e

    # ------------------------------------------------------------------
    # Webhook CRUD
    # ------------------------------------------------------------------
    def list_webhooks(self, active: bool | None = None) -> list[dict]:
        params: dict[str, Any] = {}
        if active is not None:
            params["active"] = "true" if active else "false"
        return self._request("GET", "/notifications/webhooks", params=params or None) or []

    def get_webhook(self, webhook_id: int) -> dict:
        return self._request("GET", f"/notifications/webhooks/{webhook_id}")

    def create_webhook(
        self,
        *,
        url: str,
        event_types: list[str],
        description: str,
        active: bool,
    ) -> dict:
        body = {
            "url": url,
            "event_types": event_types,
            "description": description,
            "active": active,
        }
        return self._request("POST", "/notifications/webhooks", json=body)

    def update_webhook(
        self,
        webhook_id: int,
        *,
        event_types: list[str] | None = None,
        description: str | None = None,
        active: bool | None = None,
        rotate_secret: bool = False,
    ) -> dict:
        body: dict[str, Any] = {"rotate_secret": rotate_secret}
        if event_types is not None:
            body["event_types"] = event_types
        if description is not None:
            body["description"] = description
        if active is not None:
            body["active"] = active
        return self._request("PATCH", f"/notifications/webhooks/{webhook_id}", json=body)

    def delete_webhook(self, webhook_id: int) -> None:
        self._request(
            "DELETE",
            f"/notifications/webhooks/{webhook_id}",
            expect_json=False,
        )

    # ------------------------------------------------------------------
    # Test + deliveries
    # ------------------------------------------------------------------
    def test_webhook(self, webhook_id: int, payload: dict | None = None) -> dict:
        body = {"payload": payload} if payload is not None else None
        return self._request(
            "POST",
            f"/notifications/webhooks/{webhook_id}/test",
            json=body,
        )

    def list_deliveries(
        self,
        webhook_id: int,
        *,
        limit: int = 50,
        status: str | None = None,
    ) -> list[dict]:
        params: dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        return self._request(
            "GET",
            f"/notifications/webhooks/{webhook_id}/deliveries",
            params=params,
        ) or []

    # ------------------------------------------------------------------
    # Event catalog + queue stats + retry
    # ------------------------------------------------------------------
    def list_event_types(self) -> list[dict]:
        return self._request("GET", "/notifications/events") or []

    def queue_stats(self) -> dict:
        return self._request("GET", "/notifications/queue/stats")

    def retry_delivery(self, delivery_id: int) -> dict:
        return self._request(
            "POST",
            f"/notifications/deliveries/{delivery_id}/retry",
        )

    def bulk_retry_dead(
        self,
        *,
        statuses: list[str] | None = None,
        webhook_id: int | None = None,
        limit: int = 500,
        dry_run: bool = False,
    ) -> dict:
        body: dict[str, Any] = {
            "statuses": statuses if statuses is not None else ["dead"],
            "limit": limit,
            "dry_run": dry_run,
        }
        if webhook_id is not None:
            body["webhook_id"] = webhook_id
        return self._request(
            "POST",
            "/notifications/deliveries/bulk-retry",
            json=body,
        )


__all__ = ["WebhookAdminClient", "WebhookAdminError"]
