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


# ----------------------------------------------------------
# dashboard-v2: what-if / findings history / state
# ----------------------------------------------------------
def test_whatif_overrides_change_result_without_side_effects(
    client, live_db, tmp_path, monkeypatch
):
    """극단 임계치(모든 변화가 이상)로 결과가 달라지되, 상태 파일은
    생성/변경되지 않는다 (GET = side-effect free)."""
    import shared.config as cfg
    state_file = tmp_path / "state.json"
    monkeypatch.setattr(cfg, "ANOMALY_STATE_FILE", state_file)

    base = client.get("/anomaly/scan").json()
    assert "overrides" not in base

    r = client.get(
        "/anomaly/scan",
        params={"drop_pct": 0.001, "spike_pct": 0.001, "stale_days": 1},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["overrides"] == {
        "drop_pct": 0.001, "spike_pct": 0.001, "stale_days": 1,
    }
    assert body["emitted"] is False
    assert not state_file.exists()  # 쿨다운 상태 무변경


def test_whatif_param_rejected_on_bad_value(client, live_db):
    r = client.get("/anomaly/scan", params={"drop_pct": -5})
    assert r.status_code == 422


def test_post_scan_ignores_whatif_params(client, live_db, monkeypatch):
    """POST 라우트는 오버라이드를 받지 않는다 — 알 수 없는 쿼리는 무시되고
    emit 판정은 항상 config 기준."""
    import api.notifications
    monkeypatch.setattr(api.notifications, "emit_event", lambda et, p: [])
    r = client.post(
        "/anomaly/scan", params={"emit": "false", "drop_pct": 0.001}
    )
    assert r.status_code == 200
    assert "overrides" not in r.json()


def test_findings_endpoint_shape_and_filters(client, live_db, tmp_path, monkeypatch):
    import shared.config as cfg
    from api.anomaly import store_findings
    from api.anomaly.schemas import Finding

    monkeypatch.setattr(cfg, "ANOMALY_DB_FILE", tmp_path / "anomaly.db")
    store_findings.reset_for_tests()
    store_findings.record_findings([
        Finding(kind="volume_drop", severity="critical",
                key="volume_drop:2026-07-06", message="급감", details={"q": 1}),
        Finding(kind="stale_item", severity="warning",
                key="stale_item:X1", message="미생산"),
    ])

    body = client.get("/anomaly/findings").json()
    assert body["count"] == 2
    assert body["findings"][0]["details"] in ({"q": 1}, {})  # dict 역직렬화
    assert {f["kind"] for f in body["findings"]} == {"volume_drop", "stale_item"}

    only = client.get(
        "/anomaly/findings", params={"severity": "critical"}
    ).json()
    assert [f["key"] for f in only["findings"]] == ["volume_drop:2026-07-06"]

    assert client.get("/anomaly/findings", params={"days": 0}).status_code == 422
    store_findings.reset_for_tests()


def test_state_endpoint_remaining_calc(client, live_db, tmp_path, monkeypatch):
    import time as _time

    import shared.config as cfg
    from api.anomaly import store_state

    monkeypatch.setattr(cfg, "ANOMALY_STATE_FILE", tmp_path / "state.json")
    now = _time.time()
    store_state.save_state({
        "cooldowns": {
            "fresh": now - 10,                        # 쿨다운 활성
            "expired": now - cfg.ANOMALY_COOLDOWN_SEC - 10,  # 만료
        },
        "last_scan_ts": now,
    })

    body = client.get("/anomaly/state").json()
    assert body["cooldown_sec"] == cfg.ANOMALY_COOLDOWN_SEC
    by_key = {c["key"]: c for c in body["cooldowns"]}
    assert by_key["fresh"]["active"] is True
    assert by_key["fresh"]["remaining_sec"] > 0
    assert by_key["expired"]["active"] is False
    assert by_key["expired"]["remaining_sec"] == 0
