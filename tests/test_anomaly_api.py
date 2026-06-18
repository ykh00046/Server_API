"""API tests for /anomaly endpoints."""
from __future__ import annotations


def test_rules_endpoint(client):
    r = client.get("/anomaly/rules")
    assert r.status_code == 200
    body = r.json()
    assert "drop_pct" in body
    assert "spike_pct" in body
    assert "production.anomaly.volume_drop" in body["event_types"]


def test_scan_endpoint_dry_run_default(client, live_db):
    r = client.get("/anomaly/scan")
    assert r.status_code == 200
    body = r.json()
    assert body["emitted"] is False
    assert "findings" in body
    assert isinstance(body["findings"], list)


def test_scan_endpoint_shape(client, live_db):
    body = client.get("/anomaly/scan").json()
    for key in ("scanned_at", "enabled", "count", "findings"):
        assert key in body
