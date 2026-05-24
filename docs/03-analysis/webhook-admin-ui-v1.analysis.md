# webhook-admin-ui-v1 — Analysis

> **Cycle**: webhook-admin-ui-v1
> **PDCA Phase**: Analysis (Check)
> **Date**: 2026-05-25
> **Source**: bkit:gap-detector + 회귀 테스트 결과

## 1. Match Rate: **98%**

13/13 AC 통과, 0 iterate. 설계 ↔ 구현 차이는 모두 "설계가 코드를 따라가야 할" 마이너 보강(`is_retryable_status` 함수 + `render_secret_banner_if_any` view) 두 건이며 design doc에 이미 반영.

## 2. AC 결과 표

| AC | 결과 | 핵심 증거 |
|----|:----:|----------|
| AC1 — nav 등록 | ✓ | `dashboard/app.py:71-73` "운영" 섹션 + `pages/webhooks.py` 엔트리 |
| AC2 — 큐 stats 6 카운터 | ✓ | `formatters._STATS_CARDS` 6튜플 고정 순서 + `views.render_queue_stats_section` → `st.metric` |
| AC3 — 활성/전체/비활성 필터 + 목록 | ✓ | `views.render_webhook_list_section` `st.radio` 3-way → `client.list_webhooks(active=...)` |
| AC4 — 신규 등록 폼 + secret 1회 노출 | ✓ | `views.render_register_form` 폼 + `render_secret_banner_if_any` (ack 후 `pop`) |
| AC5 — 행 액션 (toggle/edit/rotate/delete) | ✓ | `views.render_webhook_detail` 4 액션 + 각각 `_do_update/_do_rotate/_do_delete` |
| AC6 — Test ping 토스트 | ✓ | `_do_test_ping` → `toast_success(f"성공 · HTTP {rs} · {dur} ms")` |
| AC7 — deliveries 50 + status 필터 | ✓ | `views.render_deliveries_section` selectbox(`_DELIVERY_STATUSES`) + slider |
| AC8 — failed/dead retry 버튼 | ✓ | `formatters.is_retryable_status` 필터 → 버튼 + `_do_retry` |
| AC9 — 비-2xx 토스트 + 페이지 살림 | ✓ | views의 모든 `client.*` 호출 try/except `WebhookAdminError` |
| AC10 — `API_BASE_URL` 사용 | ✓ | `pages/webhooks.py:12` `from shared.config import API_BASE_URL` |
| AC11 — api_client 단위 테스트 ≥ 10 | ✓ | 18 테스트 (10 endpoint × 메서드/경로/페이로드 + 4 error path + edge) |
| AC12 — formatters 순수 함수 ≥ 6 | ✓ | 8 테스트 (cards × 2, webhook_row × 2, delivery_row × 2, truncate, parse, is_retryable) |
| AC13 — match rate ≥ 90% (목표 ≥ 95%) | ✓ | **98%** |

## 3. 회귀 결과

| 범주 | 결과 |
|------|------|
| 신규 테스트 | **29 / 29 passed** (`tests/test_webhook_admin_ui.py`) |
| 전체 main `tests/` | **287 passed**, 1 failed, 0 errors (`--basetemp=.pytest-tmp`) |
| 신규 사이클 관련 실패 | **0** |
| 사이클 무관 기존 실패 | `tests/test_rate_limiter.py::TestRateLimiterRetryAfter::test_retry_after_returns_positive_when_exceeded` — `61 <= 60` 경계 (시간 의존 flake, webhook UI와 무관) |
| 사이클 무관 사전 이슈 | `webcloring-pdf/tests/*` — selenium 미설치 (메모리에 submodule 분리 결정 기록됨) |

## 4. Zero-script QA 적용 결과

이번 사이클은 **Streamlit 페이지가 산출물의 핵심**이지만 작업 환경에 `streamlit` 모듈이 부재하여 페이지를 실제 런타임으로 띄울 수 없음. 대신 검증을 다음과 같이 대체:

- **순수 계층 단위 테스트**: 100% (29 통과)
- **AC1 nav 등록 검증**: `app.py` 소스 인스펙션 테스트 (`test_app_py_registers_webhook_page_under_operations_section`)
- **AC9 페이지 크래시 금지**: views 모듈-레벨 client 호출 검출 테스트 (`test_views_module_does_not_call_api_client_at_import_time`)
- **HTTP 라우팅 검증**: `httpx.MockTransport`로 10 엔드포인트의 메서드/경로/바디/쿼리 파라미터 전수 검증

**미수행**: 실제 Streamlit 런타임에서의 폼 입력/렌더링 검증. 운영 환경에서 1회 수동 smoke 권장 (요약: `streamlit run dashboard/app.py` 후 운영 > Webhook 관리 페이지 진입, /queue/stats 카드 표시 확인, 임의 webhook 1건 등록 → secret 노출 → ack → 삭제).

## 5. 학습 (Learnings)

1. **`dashboard/components/__init__.py`의 eager import는 streamlit-free 테스트 격리를 방해한다.**
   - 우회: `importlib.util.spec_from_file_location`로 webhook_admin 서브패키지의 순수 모듈만 직접 로드.
   - 이 우회는 자기-방어 효과도 있음 — formatters/api_client에 실수로 `import streamlit`이 들어가면 테스트가 깨짐.
   - 추후 다른 dashboard 서브패키지를 헤드리스 테스트할 때 동일 패턴 재사용 가능.

2. **secret 1회 노출은 view에서 `session_state` + 명시 ack 버튼이 가장 안전.**
   - `st.cache_*` 대상에서 분리, 로그 노출 0, ack 시 `pop`.
   - 페이지 이동만으로 사라지지 않는다는 점은 명시적 ack로 보강 (사용자가 회수했음을 확약).

3. **Streamlit 다중페이지 nav에 운영 섹션을 별도로 두는 것이 비즈니스 데이터와 운영 UI의 경계로 적합.**
   - 향후 `/metrics`, `webhook-admin-v2`, secret rotation scheduler 등 운영 UI가 모일 자리.

4. **httpx.MockTransport seam은 10 endpoint를 단일 테스트 모듈에서 가시적으로 커버할 수 있게 한다.**
   - `_Recorder` 패턴 (호출 캡처 + 스크립트 응답)을 다른 API 클라이언트에도 재사용 가능.

## 6. Risks remaining

| Risk | 영향 | 대응 |
|------|------|------|
| Streamlit 페이지의 실 런타임 검증 미수행 | UI 사소한 버그가 단위 테스트로 안 잡힐 수 있음 | 운영 환경에서 1회 수동 smoke 권장 (위 §4) |
| `/test` 동기 5s 블록 | 사용자가 답답해 두 번 클릭할 가능성 | `st.spinner` 표시 + httpx timeout 10s로 client 설정 (이미 반영) |
| dead delivery가 많을 때 retry 버튼 sprawl | UI 사용성 저하 | 표시 상위 10건 cap (이미 반영). v2에서 일괄 retry로 해결 권장 |

## 7. Files Touched

```
docs/01-plan/features/webhook-admin-ui-v1.plan.md       (+125 lines)
docs/02-design/features/webhook-admin-ui-v1.design.md   (+162 lines, +3 보강 후)
dashboard/components/webhook_admin/__init__.py          (+14 lines)
dashboard/components/webhook_admin/api_client.py        (+180 lines)
dashboard/components/webhook_admin/formatters.py        (+137 lines)
dashboard/components/webhook_admin/views.py             (+243 lines)
dashboard/pages/webhooks.py                             (+45 lines)
dashboard/app.py                                        (+3 lines, nav 등록)
tests/test_webhook_admin_ui.py                          (+339 lines)
docs/03-analysis/webhook-admin-ui-v1.analysis.md        (이 문서)
docs/04-report/webhook-admin-ui-v1.report.md            (다음)
```

신규 외부 의존성: **0**.

## 8. Recommendation

- ✓ **Match rate 98% > 95% 목표** → `bkit:report-generator`로 보고서 작성하고 `.bkit-memory.json`에 completed 등록.
- 다음 사이클 후보:
  - `webhook-admin-ui-v2`: 일괄 retry, payload 본문 모달, secret rotation 스케줄
  - `webhook-metrics-v1`: Prometheus `/metrics` exporter
  - `notifications-store-split`: `api/notifications/store.py` 577줄 분할 (refactor; PDCA 권장)
