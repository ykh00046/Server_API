---
template: design
feature: security-followup-observability
date: 2026-04-14
phase: design
parent: security-and-test-improvement
---

# security-followup-observability — Design

> **Plan**: [security-followup-observability.plan.md](../../01-plan/features/security-followup-observability.plan.md)
> **부모 사이클**: `docs/archive/2026-04/security-and-test-improvement/`
> **전략**: 최소 침습. 신규 모듈 없음. 기존 헬퍼(`_session_store.stats()`, `_load_archive_whitelist()`) 재사용.

---

## 1. 목표 요약

| ID | 목표 | 부모 Gap |
|---|---|---|
| FR-01 | `/healthz/ai` 에 sessions 블록 노출 | G3 |
| FR-02 | 통합 테스트 5종 추가 | G5 |
| FR-03 | 성능 스모크 스크립트 + 운영 매뉴얼 시간 기록 | G6 |
| FR-04 | whitelist 누락 경로 import-time 경고 | G7 |

비기능:
- 회귀 0, 테스트 128 → **133+** pass
- Match Rate ≥ 90%

---

## 2. 아키텍처 (변경 없음)

부모 사이클에서 확립한 layering 그대로:

```
api/main.py  ──(FR-01)──>  api/_session_store.stats()
api/chat.py  (no change)
shared/config.py  ──(FR-04)──>  logger.warning
tests/test_api_integration.py  ──(FR-02)──> 5 new cases
scripts/perf_smoke.py  ──(FR-03, NEW)──>  httpx sync loop
docs/specs/operations_manual.md  ──(FR-03)──>  section "테스트 벽시계 / 스모크"
```

신규 모듈: `scripts/perf_smoke.py` **한 개만**.
기존 수정: `api/main.py`, `shared/config.py`, `tests/test_api_integration.py`, `docs/specs/operations_manual.md`.

---

## 3. FR-01 — `/healthz/ai` sessions 블록

### 3.1 현재

`api/main.py` 의 `/healthz/ai` 는 Gemini 구성/키 존재 여부만 반환.

### 3.2 변경

```python
# api/main.py (healthz_ai)
from api import _session_store as _sstore

@app.get("/healthz/ai")
def healthz_ai():
    return {
        "ok": True,
        "gemini_enabled": bool(GEMINI_API_KEY),
        "model": GEMINI_MODEL,
        "sessions": _sstore.stats(),   # ← 추가
    }
```

응답 스키마:
```json
{
  "ok": true,
  "gemini_enabled": true,
  "model": "gemini-2.0-flash",
  "sessions": {
    "count": 3,
    "ttl_sec": 1800,
    "max_per_ip": 20,
    "max_total": 1000
  }
}
```

### 3.3 호환성

- 신규 키 추가만 — 기존 필드 보존
- 기존 `test_api_integration.py::test_healthz_ai` 는 `"gemini_enabled" in body` 체크이므로 무변동

---

## 4. FR-02 — 통합 테스트 5종

`tests/test_api_integration.py` 에 5개 함수 추가. 기존 TestClient / monkeypatch 구조 재사용.

| # | 테스트 | 엔드포인트 | 기대 |
|---|---|---|---|
| 1 | `test_get_record_by_item_no` | `GET /records/BW0021` | 200 또는 404 (DB 상태에 따라), dict 응답 |
| 2 | `test_summary_by_item` | `GET /summary/by_item?year=2026&month=4` | 200 list |
| 3 | `test_records_invalid_cursor` | `GET /records?cursor=not-a-cursor` | 400 |
| 4 | `test_records_bad_date` | `GET /records?start_date=bad&end_date=bad` | 400 |
| 5 | `test_rate_limit_boundary` | `/chat` 21회 연속 호출 | 마지막 호출 429 with `code=RATE_LIMITED` |

### 4.1 Rate-limit 테스트 설계

시간 의존 제거 위해 `RATE_LIMIT_CHAT` 을 3 으로 monkeypatch 하고 4번째 호출이 429 인지 검증:

```python
def test_rate_limit_boundary(client, monkeypatch, fake_gemini):
    from api import chat as chat_mod
    monkeypatch.setattr(chat_mod, "RATE_LIMIT_CHAT", 3)
    monkeypatch.setattr(chat_mod, "_rate_limit_store", {})
    for _ in range(3):
        r = client.post("/chat/", json={"message": "hi"})
        assert r.status_code == 200
    r = client.post("/chat/", json={"message": "hi"})
    assert r.status_code == 429
    assert r.json()["detail"]["code"] == "RATE_LIMITED"
```

주의: `_rate_limit_store` 이름은 실제 chat.py 내부 이름으로 확정 (Do 단계에서 grep 후 반영).

### 4.2 단건 records / by_item 엔드포인트 존재 확인

Do 단계 첫 작업으로 `api/main.py` 에서 해당 라우트 존재 확인. 없으면 테스트는 `pytest.skip` 대신 **스펙을 맞추기 위해 라우트를 추가하는 것이 아니라**, 존재하지 않으면 스킵 + analysis 에 명시 (부모 스펙 이상의 구현 확장 금지). → 범위 보호.

---

## 5. FR-03 — 성능 스모크

### 5.1 `scripts/perf_smoke.py` (NEW)

```python
"""수동 성능 스모크. CI 미편입.

사용법:
    python scripts/perf_smoke.py --url http://localhost:8000 --n 10000
측정:
    - 총 소요 시간 (wall clock)
    - RSS 증가량 (psutil, 있을 때만)
    - 2xx/4xx/5xx 카운트
"""
```

- `httpx.Client` 단일 세션
- 엔드포인트: `GET /healthz` (가벼운 경로)
- 출력: `{elapsed_sec, rss_delta_mb, counts}` JSON 한 줄

### 5.2 운영 매뉴얼 기록

`docs/specs/operations_manual.md` 말미에 섹션 추가:

```markdown
## 10. 테스트 / 스모크 벽시계 (2026-04-14 기준)

- pytest 전체: {N}s / 133 tests
- 10k /healthz 스모크: {elapsed}s, RSS +{delta}MB
- 측정 환경: Windows 11, uvicorn --workers 1
```

값은 Do 단계에서 실제 측정치로 채움.

---

## 6. FR-04 — whitelist import-time 경고

### 6.1 현재

```python
# shared/config.py
def _load_archive_whitelist() -> tuple[Path, ...]:
    raw = os.getenv("ARCHIVE_DB_WHITELIST", "").strip()
    if not raw:
        return (ARCHIVE_DB_FILE.resolve(),)
    items: list[Path] = []
    for part in raw.split(";"):
        p = part.strip()
        if p:
            items.append(Path(p).resolve())
    return tuple(items) if items else (ARCHIVE_DB_FILE.resolve(),)
```

### 6.2 변경

```python
import logging
_logger = logging.getLogger(__name__)

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
```

**중요**: 경고만 출력, 리스트에는 포함 (런타임 `resolve_archive_db()` 에서 여전히 `exists()` 체크로 차단). 즉 부팅은 성공, 접근 시 `INVALID_ARCHIVE_PATH`.

### 6.3 테스트

```python
# tests/test_archive_whitelist.py 에 추가
def test_missing_whitelist_entry_warns(monkeypatch, caplog, tmp_path):
    missing = tmp_path / "nope.db"
    monkeypatch.setenv("ARCHIVE_DB_WHITELIST", str(missing))
    import importlib, shared.config as cfg
    with caplog.at_level("WARNING", logger="shared.config"):
        importlib.reload(cfg)
    assert any("not found at import" in r.message for r in caplog.records)
```

reload 후 원복 필요 → fixture 로 `importlib.reload(cfg)` 한 번 더 호출.

---

## 7. 에러 코드 (변경 없음)

부모 §6.1 유지. 신규 코드 추가 없음.

---

## 8. 테스트 매트릭스

| 파일 | 기존 | 추가 | 합계 |
|---|---|---|---|
| `test_api_integration.py` | 12 | +5 | 17 |
| `test_archive_whitelist.py` | 9 | +1 | 10 |
| `test_session_store.py` | 6 | 0 | 6 |
| 기타 기존 | 101 | 0 | 101 |
| **전체** | **128** | **+6** | **134** |

---

## 9. 파일 맵 (§11.1)

| 상태 | 파일 | 변경 |
|---|---|---|
| MOD | `api/main.py` | `/healthz/ai` 에 sessions 블록 |
| MOD | `shared/config.py` | `_load_archive_whitelist()` warning |
| MOD | `tests/test_api_integration.py` | +5 tests |
| MOD | `tests/test_archive_whitelist.py` | +1 test |
| MOD | `docs/specs/operations_manual.md` | §10 스모크 섹션 |
| NEW | `scripts/perf_smoke.py` | 수동 10k 스모크 |

신규 모듈 1개, 수정 5개.

---

## 10. 구현 순서

1. FR-04 (가장 격리) → `test_archive_whitelist.py` 회귀 확인
2. FR-01 → `/healthz/ai` 스키마 테스트 추가 (기존 `test_healthz_ai` 확장)
3. FR-02 → 5 테스트. 없는 엔드포인트는 **스킵 + analysis 기록** (범위 보호)
4. FR-03 → `scripts/perf_smoke.py` 작성, 로컬 1회 측정, operations_manual 기록
5. `/pdca analyze security-followup-observability`

---

## 11. 리스크

| 리스크 | 완화 |
|---|---|
| `importlib.reload(shared.config)` 이 다른 테스트에 누수 | caplog 테스트 종료 시 env 원복 + reload |
| 21회 호출 테스트의 전역 `_rate_limit_store` 상태 오염 | monkeypatch 로 빈 dict 치환 |
| perf_smoke 의존성(`psutil`) 없을 수 있음 | 선택적 import, 없으면 RSS 출력 생략 |
