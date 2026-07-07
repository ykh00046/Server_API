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


def test_get_scan_never_emits(client, live_db):
    """GET은 side-effect free — 과거의 ?emit=true 쿼리는 무시된다
    (full-review-202607: 프록시/프리페처가 GET으로 발행 유발 가능)."""
    r = client.get("/anomaly/scan", params={"emit": "true"})
    assert r.status_code == 200
    assert r.json()["emitted"] is False


def test_post_scan_exists_and_preview_mode(client, live_db):
    """발행 트리거는 POST로 분리. emit=false면 미리보기와 동일."""
    r = client.post("/anomaly/scan", params={"emit": "false"})
    assert r.status_code == 200
    body = r.json()
    assert body["emitted"] is False
    assert "findings" in body
