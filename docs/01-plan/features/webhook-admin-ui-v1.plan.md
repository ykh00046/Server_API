# webhook-admin-ui-v1 — Plan

> **Cycle**: webhook-admin-ui-v1
> **PDCA Phase**: Plan
> **Date**: 2026-05-25
> **Predecessors**: webhook-notifications-v1 (백엔드 CRUD), webhook-async-dispatch-v2 (큐+backoff)

## 1. Background

`webhook-notifications-v1`과 `webhook-async-dispatch-v2`로 백엔드 webhook 서브시스템은 운영 가능한 상태이지만, 운영자는 여전히 `curl`/HTTPie로 직접 API를 호출해야 함:

| 운영 액션 | 현재 방법 |
|---|---|
| webhook 등록 | `POST /notifications/webhooks` curl |
| 활성/비활성 토글 | `PATCH` curl |
| 등록된 webhook 목록 보기 | `GET` curl + jq |
| 최근 delivery 결과 보기 | `GET .../deliveries` curl + jq |
| 실패한 delivery 재시도 | `POST .../retry` curl |
| 큐 상태 (queued/dead/retrying) 확인 | `GET /queue/stats` curl |

이 마찰은 webhook 기능 채택을 늦추고, secret 노출 위험(터미널 히스토리)을 만든다. Streamlit 대시보드(`dashboard/`)에 webhook 관리 페이지를 추가해 모든 액션을 GUI로 제공한다.

## 2. Goal

운영자가 **터미널 없이** webhook 등록/조회/편집/삭제/테스트/재시도/큐 모니터링을 수행할 수 있는 Streamlit 페이지를 추가한다. 신규 외부 의존성 0.

## 3. Non-Goals (defer to v2+)

- 다중 delivery 일괄 재시도 (단건만)
- delivery payload/response 전체 본문 모달 (요약 컬럼만)
- secret rotation 스케줄링/자동 알림
- 권한/인증 (현 대시보드 정책 그대로 — LAN 신뢰 가정)
- SSE/실시간 푸시 (수동 새로고침)
- Prometheus `/metrics` exporter (별도 사이클 권장)

## 4. Dependencies

| 종류 | 항목 | 상태 |
|------|------|------|
| Python | `httpx` (이미 requirements.txt) | ✅ |
| Python | `streamlit` (이미) | ✅ |
| Config | `shared.config.API_BASE_URL` (이미 존재, 기본 `http://localhost:8000`) | ✅ |
| API | webhook CRUD/test/deliveries/events/queue 라우트 10개 | ✅ (v1+v2) |
| Module | `dashboard.components.notifications` (토스트) | ✅ |
| 신규 외부 의존성 | — | **0** |

## 5. Acceptance Criteria

| # | Criterion |
|---|-----------|
| AC1 | `dashboard/app.py` 내비에 "운영 > Webhook 관리" 페이지가 등록되어 nav.run으로 로드된다 |
| AC2 | 페이지 헤더 영역에 `/queue/stats`의 6 카운터를 카드 형태로 표시한다 (queued/in_flight/retrying/success_24h/failure_24h/dead) |
| AC3 | 활성/전체/비활성 라디오 필터링된 webhook 목록을 표 형태로 표시한다 (id/url/events/active/created_at) |
| AC4 | "신규 등록" expander에서 url/event_types(multiselect, `/events`에서 로드)/description/active 입력 후 제출 시 secret을 1회 노출하는 UI를 보여준다 |
| AC5 | 각 webhook 행에서 액션 가능: active toggle / event_types & description 편집 / rotate_secret / delete |
| AC6 | webhook 단위 "Test ping" 버튼 → 응답 status, response_status, duration_ms 토스트 |
| AC7 | webhook 선택 시 최근 deliveries 50개 + status 필터 표 |
| AC8 | failed/dead delivery에 "재시도" 버튼 → 성공 시 토스트 + 표 새로고침 |
| AC9 | API 비-2xx 응답은 에러 토스트로 사용자에게 노출, 페이지 크래시 금지 |
| AC10 | API base URL은 `shared.config.API_BASE_URL`을 따른다 (env override 가능) |
| AC11 | API 클라이언트 단위 테스트: httpx `MockTransport`로 10 엔드포인트 전부 경로/메서드/페이로드 검증 (≥ 10 테스트) |
| AC12 | formatter 순수 함수 (`format_queue_stats_cards`, `format_delivery_row`, `format_webhook_row`)는 입력→출력 결정적, Streamlit import 없이 단위 테스트 (≥ 6 테스트) |
| AC13 | gap-detector match rate ≥ 90% (목표 ≥ 95%) |

## 6. Constraints / Risks

- **CORS**: Streamlit이 동일 호스트에서 FastAPI를 호출 → `shared.config.CORS_ORIGINS`에 이미 `localhost:8502` 포함. 추가 변경 불필요.
- **Secret 1회 노출**: `WebhookCreated`/`rotate_secret` 응답에만 평문 secret. 페이지 새로고침 시 사라져야 함 → `st.session_state`에 짧은 시간만 유지.
- **장시간 응답**: dispatcher가 5s timeout, `/test`는 동기 호출이므로 최대 ~5s 블록. 사용자에게 spinner 표시 필수.
- **테스트 격리**: Streamlit page는 `st.runtime` 의존이라 직접 import 불가 — 헤드리스 테스트 대상은 api_client + formatters로 한정한다.
- **호환성**: 백엔드 라우트/스키마 변경 없음. 추가만 한다.

## 7. Out-of-band Notes

- `streamlit-shadcn-ui`가 requirements에 있지만 일관성을 위해 native Streamlit 위젯만 사용 (페이지 전체에서 단일 스타일).
- `dashboard/pages/`의 기존 4페이지(overview/trends/batches/products)는 비즈니스 데이터 페이지. 운영 페이지가 처음 들어가는 사이클이므로 새 섹션 "운영"을 만든다.
