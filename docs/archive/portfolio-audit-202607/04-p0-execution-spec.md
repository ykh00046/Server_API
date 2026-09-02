# P0-1 실행 지시서 — 인증 활성화를 위한 클라이언트 준비 (auth-enable-v2)

> **상태: ✅ 완료** (2026-07-15) — 구현·병합·push 완료(`main` bbcbe99, 대시보드 HTTP 클라이언트 헤더 정렬). 서버 auth 전환(`API_AUTH_ENABLED=true`)은 스코프대로 10월 재검토 회부. 운영 반영은 운영 PC `update.bat` 별도.

> 작성일: 2026-07-12 · 대상: `C:\X\Server_API` (+ 서브모듈 `webcloring-pdf`)
> 선행 문서: [01-improvement-plan.md](01-improvement-plan.md) §3 P0-1, [02-design.md](02-design.md) §3.3,
> `docs/01-plan/features/roadmap-2026h2.plan.md` B-1 (서버 전환 자체는 보류 — 2026-10 재검토 결정 존중)
> 본 지시서의 코드 인용은 2026-07-12 실코드 확인 결과다.

---

## 1. 목표와 배경

서버 측 인증은 완성돼 있다: `shared/auth.py`(opt-in, 상수시간 비교, `PUBLIC_PATHS` SSOT) +
`api/main.py`의 `auth_and_audit` 미들웨어 + `api/_audit.py` 감사 로그, 그리고 `tests/test_auth.py`·
`tests/test_audit.py`가 이를 고정한다. 그러나 `API_AUTH_ENABLED=false`(shared/config.py:148 기본)로
실사용이 0이고, **클라이언트 측이 미정렬**이다: 대시보드의 HTTP 호출 4개 파일 중 2개
(`dataset_page.py`, `views/anomaly.py`)만 `X-API-Key` 헤더를 지원하고, `webhook_admin/api_client.py`와
`ai_section.py`(챗 SSE)는 무헤더다. 본 과제는 모든 클라이언트 호출 지점을 공용 헤더 헬퍼
`shared/api_client.py:auth_headers()`로 정렬해, 이후 인증 전환이 운영 `.env` 한 줄
(`API_AUTH_ENABLED=true`)이 되게 한다. 헤더는 auth 비활성 서버에서 무시되므로 선배포가 무위험이라는
점이 이 설계의 핵심이다. 운영 전환(auth ON) 자체는 이 과제의 스코프가 아니다 — 리허설 절차(§6)를
문서·검증까지 준비해 10월 재검토에 회부한다.

---

## 2. 사전 조건

1. 작업 브랜치 분기. 기준 게이트 green 확인:
   ```bash
   python -m pytest tests -q        # ≈630 케이스
   ruff check .
   ```
2. 서버 측 인증 계약 재확인(코드 리딩만, 수정 금지):
   - `shared/auth.py`: `X-API-Key: <key>` 또는 `Authorization: Bearer <token>`, `PUBLIC_PATHS =
     {"/", "/healthz", "/healthz/ai", "/docs", "/redoc", "/openapi.json"}` — **`/metrics`·`/chat/*`·
     `/notifications/*`·`/materials/*`·`/anomaly/*`는 전부 보호 대상**이다.
   - `api/main.py:113` `auth_and_audit` 미들웨어: OPTIONS·public path 통과, 실패 시 401 + 감사 DENY.
   - `shared/config.py:148-154`: `API_AUTH_ENABLED`, `API_KEYS`(콤마 구분), `API_BEARER_TOKENS`.
3. ⚠️ 운영 대시보드는 라이브 실데이터(`database/production_analysis.db`)를 본다 — **변경성 기능의
   수동 테스트(webhook 생성/삭제, 문서 삭제, `/materials/run`)는 운영 PC 라이브 환경에서 하지 않는다.**
   검증은 pytest(MockTransport/fixture DB)와 §6 리허설 체크로 한정.

---

## 3. 호출 지점 전수 목록 (실코드 확정)

### 3.1 헤더 정렬 대상 (변경 필요)

| # | 파일 | 호출 | 현행 상태 |
|---|---|---|---|
| C1 | `dashboard/components/webhook_admin/api_client.py` | `WebhookAdminClient` — `/notifications/webhooks` CRUD, test, deliveries, events, queue/stats, bulk-retry (11개 메서드, 전부 `self._client.request` 단일 경로 :80-112) | **무헤더** |
| C2 | `dashboard/components/ai_section.py:99` | `_stream_chat_tokens_once` — `httpx.stream("POST", {API_BASE_URL}/chat/stream)` | **무헤더** |
| C3 | `dashboard/dataset_page.py:40-45, 83-131` | `_headers()` + `_fetch`(GET `{prefix}`), `_fetch_runs`(GET `{prefix}/runs`), `_trigger_run`(POST `{prefix}/run`), `_delete`(DELETE `{prefix}/{doc_number}`) — materials/binder 공용 | 자체 `_headers()` (`MATERIALS_API_KEY` → `DASHBOARD_API_KEY` 순) — **공용 헬퍼로 위임 교체** |
| C4 | `dashboard/views/anomaly.py:36-57` | `_headers()` + `_fetch`/`_fetch_fresh` — GET `/anomaly/state`, `/anomaly/scan` 등 | C3과 동일한 `_headers()` 사본 — **위임 교체 (중복 제거)** |

C1의 소비처는 `dashboard/views/webhooks.py:26, 31`의 `WebhookAdminClient(API_BASE_URL)` 2곳 —
클라이언트 생성자에 기본값을 넣으면 **소비처 무수정**.

### 3.2 이미 준비 완료 (코드 변경 불필요 — 확인만)

| 파일 | 근거 |
|---|---|
| `webcloring-pdf/src/services/api_backup_manager.py:54-59` (봇) | `_headers()`가 이미 `X-API-Key` 첨부. 키 소스: env `MATERIALS_API_KEY` 우선, 없으면 config 파일 `api_key` (`src/config/api_backup_config.py:64-65`). POST `{base_url}{backup_path}`(/materials/backup·/binder/backup)에 적용됨 |
| `webcloring-pdf/src/services/health_checker.py` | `GET /healthz`만 호출 — public path, 키 불필요 |
| `webcloring-pdf/src/core/api_client.py` | Server_API가 아니라 **그룹웨어 포털** API 클라이언트 — 대상 아님 |

### 3.3 대상 아님 (혼동 방지용 명시)

| 항목 | 이유 |
|---|---|
| `dashboard/data.py` 및 views의 DBRouter 조회 전부 | HTTP가 아닌 SQLite 직접 접근(`mode=ro`) — 설계 원칙(`system_architecture.md` §4)상 유지 |
| `api/notifications/dispatcher.py`, `worker.py`, `events.py` | **outbound** webhook 발신(외부 수신처로) — 자기 API 호출 아님 |
| `tools/watcher.py`, `api/anomaly/*` | in-process/DB 접근 — HTTP 없음 |
| `manager.py` | 자식 프로세스 기동/종료만 — API HTTP 호출 없음 |
| `tools/smoke_api.sh` | pytest + import 체크 + `curl /healthz`(public)만 — 변경 불필요 |
| `scripts/perf_smoke.py` | 기본 `/healthz`(public). 보호 경로 측정이 필요해질 때 `--api-key` 옵션 추가는 후속(선택) — 본 과제 범위 밖 |

---

## 4. 변경 목록

### 4.1 신규 `shared/api_client.py` — 공용 헤더 헬퍼 (소형, 순수 함수)

```python
# shared/api_client.py
"""Dashboard-side HTTP auth header helper (auth-enable-v2).

Server auth (shared/auth.py) accepts ``X-API-Key``. When the server runs with
``API_AUTH_ENABLED=false`` (current default) the header is ignored, so it is
always safe to attach. Pure function — no Streamlit/FastAPI import (coverage
측정 대상, coverage omit에 넣지 않는다).
"""
from __future__ import annotations

import os


def auth_headers() -> dict[str, str]:
    """Return ``{"X-API-Key": <key>}`` if a dashboard API key is configured, else ``{}``.

    Key precedence: ``DASHBOARD_API_KEY`` (canonical, dashboard-wide) >
    ``MATERIALS_API_KEY`` (legacy — dataset_page가 먼저 도입한 이름, 봇과 공유).
    """
    api_key = os.getenv("DASHBOARD_API_KEY") or os.getenv("MATERIALS_API_KEY")
    if api_key:
        return {"X-API-Key": api_key.strip()}
    return {}
```

주의: 기존 `dataset_page._headers()`는 `MATERIALS_API_KEY`를 먼저 봤다. 공용 헬퍼는
`DASHBOARD_API_KEY`를 정본으로 승격한다 — 두 키를 **같은 값**으로 운영하면(§6) 차이가 없고,
운영 `.env`에 현재 두 키 모두 미설정이므로 실환경 동작 변화는 0이다. 이 우선순위 변경을
docstring과 본 지시서에 명시했으므로 추가 호환 코드는 만들지 않는다.

### 4.2 `dashboard/components/webhook_admin/api_client.py` — 생성자에 headers 주입 (C1)

```python
from shared.api_client import auth_headers

class WebhookAdminClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
        headers: dict[str, str] | None = None,      # 신설 — None이면 auth_headers()
    ):
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            transport=transport,
            headers=auth_headers() if headers is None else headers,
        )
```

- 11개 공개 메서드와 `_request` 시그니처 불변 — 헤더는 `httpx.Client` 기본 헤더로 전 요청에 적용.
- 소비처 `views/webhooks.py` 무수정.
- 모듈 docstring의 "Sole IO layer" 계약 유지 — 헤더 로직도 이 파일 밖으로 새지 않게 생성자 한 곳에만.

### 4.3 `dashboard/components/ai_section.py` — 챗 SSE에 헤더 추가 (C2)

```python
from shared.api_client import auth_headers   # import 블록에 추가

def _stream_chat_tokens_once(stream_url: str, payload: dict) -> Iterator[str]:
    with httpx.stream(
        "POST", stream_url, json=payload, timeout=60.0, headers=auth_headers()
    ) as r:
        ...  # 이하 무변경
```

한 줄 변경. `_stream_chat_tokens`(재시도 래퍼)·렌더 함수는 무변경.

### 4.4 `dashboard/dataset_page.py` — `_headers()`를 위임으로 교체 (C3)

```python
from shared.api_client import auth_headers

def _headers() -> dict:
    return auth_headers()
```

`_fetch`/`_fetch_runs`/`_trigger_run`/`_delete`의 `headers=_headers()` 호출부는 무변경
(로컬 이름 유지 — 이 파일을 참조하는 기존 테스트/관례 보호). `import os`가 다른 용도로
안 쓰이면 제거(ruff F401이 알려줌).

### 4.5 `dashboard/views/anomaly.py` — 동일 위임 교체 (C4)

4.4와 동일 패턴: 파일 내 `_headers()` 본문을 `return auth_headers()`로 교체, 불용 import 정리.
`_fetch`(`@st.cache_data(ttl=60)`)·`_fetch_fresh` 호출부 무변경.

### 4.6 `.env.example` — 키 문서화

`MATERIALS_API_KEY=` 항목(이미 존재) 아래에 추가:

```bash
# (선택) 대시보드 전 페이지(웹훅 관리·AI 챗·자재·이상탐지)가 API 호출 시 보낼 키.
# API_AUTH_ENABLED=true 전환 시 API_KEYS 중 하나와 같은 값으로 설정.
# 미설정 시 MATERIALS_API_KEY를 fallback으로 사용.
DASHBOARD_API_KEY=
```

### 4.7 봇(webcloring-pdf) — 코드 무변경, 확인 항목만

서브모듈은 이 사이클에서 커밋하지 않는다. 다음만 확인·기록:
- `ApiBackupConfig.get_api_key()`가 env `MATERIALS_API_KEY`를 읽으므로, 전환 시 봇 실행 환경
  (`webcloring-pdf/.env` 또는 manager가 전달하는 env)에 같은 키를 넣으면 끝.
- `is_configured()`(api_backup_config.py:114)는 api_key를 필수로 요구하지 않음 — auth OFF에서 현행 유지.

---

## 5. 테스트 계획

### 5.1 신규 테스트

**`tests/test_api_client_headers.py` (신규 — `shared/api_client.py` 단위):**

| # | 케이스 | 기대 |
|---|---|---|
| T1 | 두 env 모두 없음 (monkeypatch.delenv) | `auth_headers() == {}` |
| T2 | `DASHBOARD_API_KEY=abc` | `{"X-API-Key": "abc"}` |
| T3 | `MATERIALS_API_KEY=legacy`만 설정 | `{"X-API-Key": "legacy"}` (fallback) |
| T4 | 둘 다 설정 | `DASHBOARD_API_KEY` 우선 |
| T5 | 키에 공백 포함 `" abc "` | strip 되어 `"abc"` |

**`tests/test_webhook_admin_ui.py` 확장 (기존 파일 — MockTransport seam 활용):**

| # | 케이스 | 기대 |
|---|---|---|
| T6 | `DASHBOARD_API_KEY` 설정 + `WebhookAdminClient` 기본 생성 → `list_webhooks()` | MockTransport가 받은 요청에 `X-API-Key` 헤더 존재 |
| T7 | 키 미설정(무토큰 시나리오) | 요청에 `X-API-Key` 부재 — 기존 테스트 전부 무수정 green (헤더 없음 = 현행 동일) |
| T8 | `headers={...}` 명시 주입 | 주입값이 auth_headers()를 대체 |

**무토큰/오키 접근 시나리오 (서버 측 — 기존 `tests/test_auth.py`·`test_audit.py`가 이미 커버하는지
확인 후, 미들웨어 통합 케이스가 없으면 `tests/test_auth.py`에 추가):**

| # | 케이스 | 기대 |
|---|---|---|
| T9 | `API_AUTH_ENABLED=true` + `API_KEYS=["k1"]` monkeypatch, TestClient `GET /records` 무헤더 | 401 + `WWW-Authenticate: Bearer` |
| T10 | 같은 조건, `X-API-Key: wrong` | 401 (reason=invalid_credentials 감사 DENY) |
| T11 | 같은 조건, `X-API-Key: k1` | 200 |
| T12 | 같은 조건, `GET /healthz` 무헤더 | 200 (PUBLIC_PATHS) |
| T13 | auth ON + 대시보드 헬퍼 조합: `auth_headers()` 반환값을 그대로 TestClient 헤더로 전달해 보호 경로 200 | 클라이언트-서버 계약의 end-to-end 고정 |

> XFF 위조류 시나리오는 이 프로젝트엔 해당 없음(IP 기반 신뢰 없음 — 키/토큰 매칭만).
> 401 발생원 추적은 `api/_audit.py`의 DENY 로그(client_ip 포함)가 담당한다는 것을 T10에서 caplog로 확인.

### 5.2 기존 게이트 실행 명령

```bash
python -m pytest tests -q     # 전체 ≈630 + 신규. auth OFF 기본에서 기존 테스트 무수정 green이 계약
ruff check .                  # F/BLE001/I/UP/B/SIM/E501 (+C901 잠금 3파일)
# CI: coverage floor 88 — shared/api_client.py는 omit에 넣지 말 것 (신규 파일은 측정 대상 관례)
```

---

## 6. 전환 리허설 시퀀스 (이 과제의 산출물 — 실행은 10월 재검토 이후)

각 단계의 롤백은 직전 단계로 되돌리는 것이다.

1. **클라이언트 선배포** (본 과제 완료 시점): §4 변경 배포(`update.bat` + 매니저 재시작).
   서버 auth OFF이므로 헤더는 무시됨 — 무위험. 대시보드 전 페이지 정상 동작 확인.
2. **키 발급**: 운영 `.env`에
   ```bash
   API_KEYS=<random 32B+ 1개>        # 서버가 수락할 키 목록
   DASHBOARD_API_KEY=<같은 값>        # 대시보드 발신 키
   MATERIALS_API_KEY=<같은 값>        # 봇 발신 키 (봇 실행 환경에도 반영)
   ```
   아직 `API_AUTH_ENABLED`는 false — 동작 무변화.
3. **활성화**: `API_AUTH_ENABLED=true` + 매니저에서 API 재시작.
4. **검증 체크리스트** (라이브 조회는 읽기 전용 경로만):
   - `curl http://localhost:8000/healthz` → 200 (public)
   - `curl http://localhost:8000/records` → 401 / `curl -H "X-API-Key: <키>" .../records` → 200
   - 대시보드: overview(DB 직접 — 영향 없음이 정상), 자재요청/바인더 조회, 이상탐지 조회,
     웹훅 목록 **조회**, AI 챗 질문 1건 — 전부 정상
   - 봇: 다음 정기 백업 1회 성공 (`{prefix}/runs` 이력으로 확인)
   - `logs/`의 `[AUDIT] DENY` 발생원 0 확인 — DENY가 있으면 빠뜨린 클라이언트이며 ip/path로 즉시 식별 가능
5. **실패 시 롤백**: `.env`에서 `API_AUTH_ENABLED=false` 한 줄 + API 재시작.

---

## 7. 수용 기준 (체크리스트)

- [ ] `shared/api_client.py` 신설, `auth_headers()` 단위 테스트 T1~T5 green
- [ ] 대시보드의 Server_API HTTP 호출 지점 **4파일 전부**(C1~C4)가 `auth_headers()`를 경유하며, 그 외 HTTP 호출 지점이 없음을 재확인 (`grep -rn "httpx" dashboard/` 결과가 이 4파일뿐)
- [ ] `WebhookAdminClient` 기본 생성 시 키 설정이면 전 요청에 `X-API-Key` 첨부, 소비처(`views/webhooks.py`) 무수정 (T6~T8)
- [ ] auth OFF(기본) 상태에서 기존 테스트 ≈630개 **무수정** green — 동작 불변 증명
- [ ] auth ON 통합 케이스 T9~T13 green (없던 것만 추가, 기존 test_auth.py와 중복 금지)
- [ ] `.env.example`에 `DASHBOARD_API_KEY` 문서화
- [ ] 봇 측: 코드 변경 0, `MATERIALS_API_KEY` 주입 경로 확인 결과가 본 문서/plan에 기록됨
- [ ] ruff 전 게이트 + CI coverage floor 88 유지 (`shared/api_client.py` omit 미등재)
- [ ] §6 리허설 시퀀스가 검증 체크리스트까지 포함해 문서화됨 (10월 재검토 회부 자료)

---

## 8. 하지 말 것 (스코프 밖)

- **서버 인증 로직 수정 금지** — `shared/auth.py`, `PUBLIC_PATHS`, `api/main.py` 미들웨어 순서, `api/_audit.py`는 완성·테스트 고정 상태. 한 줄도 건드리지 않는다.
- **운영 auth ON 전환 실행 금지** — `API_AUTH_ENABLED=true`는 2026-10 재검토 결정 사항. 본 과제는 리허설 준비까지.
- **대시보드 DB 직접 접근의 API 경유 전환 금지** — `system_architecture.md` §4.4 결정(장애 격리) 유지. `data.py`에 손대지 않는다.
- **RBAC/사용자별 키/키 로테이션 체계 도입 금지** — 운영자 1인 전제(roadmap C-2 기준 미충족).
- **webcloring-pdf 서브모듈 코드 변경 금지** — 이미 키 지원 완료. 필요 시 별도 서브모듈 사이클.
- **운영 PC 라이브 대시보드에서 변경성 기능(webhook 생성/삭제·문서 삭제·`/materials/run`) 수동 테스트 금지** — MockTransport/fixture DB로만 검증.
- **`requirements*.txt` 변경 금지** — 신규 의존성 없음 (httpx·dotenv 기존 보유).

---

## 9. 롤백 방법

| 상황 | 조치 | 효과 |
|---|---|---|
| (미래) auth ON 후 401 장애 | `.env` `API_AUTH_ENABLED=false` 한 줄 + 매니저에서 API 재시작 | 즉시 open-access 복원. 클라이언트 헤더는 무시되므로 잔존해도 무해 |
| 특정 클라이언트만 401 | 롤백 불필요 — `[AUDIT] DENY` 로그의 ip/path로 발신원 식별 → 해당 env에 키 주입 | 부분 수복 |
| 키 유출 의심 | `.env` `API_KEYS` 값 교체 + `DASHBOARD_API_KEY`/`MATERIALS_API_KEY` 동시 교체 + 재시작 | 키 회전 (본 과제 범위의 수동 절차) |
| 본 과제 코드 자체 롤백 | 해당 커밋 revert — 클라이언트 5파일(+테스트)만이므로 서버 동작과 독립 | auth OFF 환경에선 revert 전후 동작 동일 |

핵심 불변식: **어떤 단계에서도 서버 `.env` 한 줄(`API_AUTH_ENABLED`)이 유일한 전환/롤백 스위치**이고,
클라이언트 헤더 첨부는 서버 상태와 무관하게 항상 안전하다.
