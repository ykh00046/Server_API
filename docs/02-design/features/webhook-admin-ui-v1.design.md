# webhook-admin-ui-v1 — Design

> **Cycle**: webhook-admin-ui-v1
> **PDCA Phase**: Design
> **Date**: 2026-05-25
> **Plan**: `docs/01-plan/features/webhook-admin-ui-v1.plan.md`

## 1. Module Layout

```
dashboard/
  app.py                                  # +1 nav 섹션 추가 (≤ 6 라인 diff)
  pages/
    webhooks.py                           # NEW — Streamlit page orchestration
  components/
    webhook_admin/                        # NEW package
      __init__.py                         # public re-exports
      api_client.py                       # httpx client (모든 IO 여기로)
      formatters.py                       # 순수 함수 (Streamlit import 금지)
      views.py                            # st.* 렌더링 (orchestration 헬퍼)
tests/
  test_webhook_admin_ui.py                # NEW — api_client + formatters 단위 테스트
```

**층 분리 원칙**:
- **`api_client.py`**: HTTP/JSON ↔ Python dict. 예외는 `WebhookAdminError(message, status, body)` 단일 타입으로 정규화. Streamlit import 금지.
- **`formatters.py`**: dict→dict 또는 dict→str. 부수 효과/IO 없음. 단위 테스트 100% 결정적.
- **`views.py`**: `st.*` 위젯 + 상태(`st.session_state`) + 에러 토스트. api_client 호출 결과를 formatters로 변환 후 위젯에 바인딩.
- **`pages/webhooks.py`**: 페이지 진입점. 위 3개 모듈을 조립.

## 2. API Client (`api_client.py`)

### 2.1 Public surface

```python
class WebhookAdminError(Exception):
    """비-2xx 응답 또는 네트워크 장애. status=None은 네트워크."""
    def __init__(self, message: str, *, status: int | None = None, body: str | None = None): ...

class WebhookAdminClient:
    def __init__(self, base_url: str, *, timeout: float = 10.0, transport: httpx.BaseTransport | None = None): ...
    # CRUD
    def list_webhooks(self, active: bool | None = None) -> list[dict]: ...
    def get_webhook(self, webhook_id: int) -> dict: ...
    def create_webhook(self, *, url: str, event_types: list[str], description: str, active: bool) -> dict: ...
    def update_webhook(self, webhook_id: int, *, event_types=None, description=None, active=None, rotate_secret=False) -> dict: ...
    def delete_webhook(self, webhook_id: int) -> None: ...
    # Test + deliveries
    def test_webhook(self, webhook_id: int, payload: dict | None = None) -> dict: ...
    def list_deliveries(self, webhook_id: int, *, limit: int = 50, status: str | None = None) -> list[dict]: ...
    # Events catalog + queue stats + retry
    def list_event_types(self) -> list[dict]: ...
    def queue_stats(self) -> dict: ...
    def retry_delivery(self, delivery_id: int) -> dict: ...
```

### 2.2 Error normalization

| 응답 | client 동작 |
|------|------------|
| 2xx with JSON | dict/list 반환 |
| 2xx no body (DELETE) | `None` |
| 4xx/5xx | `WebhookAdminError(message=detail, status=resp.status_code, body=resp.text)` |
| `httpx.TimeoutException` | `WebhookAdminError("request timed out", status=None)` |
| `httpx.TransportError` | `WebhookAdminError(str(e), status=None)` |

`detail` 추출: response가 JSON이고 `detail` 키가 있으면 그 값, 아니면 `resp.text[:200]`.

### 2.3 Test seam

생성자는 `transport: httpx.BaseTransport | None`를 받음. None이면 기본 transport, 테스트는 `httpx.MockTransport`를 주입.

## 3. Formatters (`formatters.py`)

순수 함수만:

```python
def format_queue_stats_cards(stats: dict) -> list[tuple[str, int, str]]:
    """Return [(label, value, color_hint), ...] 6 entries in fixed order."""

def format_webhook_row(wh: dict) -> dict:
    """Truncate url, format created_at, render event_types as comma string."""

def format_delivery_row(d: dict) -> dict:
    """Status emoji prefix, truncated error/response_body, human duration."""

def truncate(text: str, limit: int) -> str:
    """Backing utility — '…' 단일 문자 사용."""

def parse_event_types_input(raw: str) -> list[str]:
    """Comma/newline-separated UI input → sanitized list."""
```

규칙:
- 절대 `st.*` import 금지
- 입력이 비어/누락이면 빈 문자열 또는 `'-'` 반환 (UI 표시용 안전 기본값)

## 4. Views (`views.py`)

함수만 export (클래스 X):

```python
def render_queue_stats_section(client) -> None: ...
def render_webhook_list_section(client) -> int | None:
    """선택된 webhook_id 반환 (없으면 None)"""
def render_register_form(client, event_catalog: list[dict]) -> None: ...
def render_webhook_detail(client, webhook_id: int, event_catalog: list[dict]) -> None: ...
def render_deliveries_section(client, webhook_id: int) -> None: ...
```

각 view 함수는 자체 try/except로 `WebhookAdminError`를 잡고 `toast_error(...)`로 노출한다. 페이지는 절대 크래시하지 않는다.

## 5. Page (`pages/webhooks.py`)

```python
import streamlit as st
from shared.config import API_BASE_URL
from components.webhook_admin import WebhookAdminClient, views

client = WebhookAdminClient(API_BASE_URL)

st.title("🔔 Webhook 관리")
views.render_queue_stats_section(client)

# 이벤트 카탈로그는 한 번만 로드 (cache_resource)
@st.cache_resource(ttl=60)
def _event_catalog():
    return client.list_event_types()

views.render_register_form(client, _event_catalog())

selected_id = views.render_webhook_list_section(client)
if selected_id is not None:
    views.render_webhook_detail(client, selected_id, _event_catalog())
    views.render_deliveries_section(client, selected_id)
```

## 6. Nav Integration

`dashboard/app.py`에 새 섹션 한 줄 추가:

```python
pages = {
    "대시보드": [...],
    "생산 관리": [...],
    "운영": [
        st.Page("pages/webhooks.py", title="Webhook 관리", icon="🔔"),
    ],
}
```

## 7. State / Secret Display

`st.session_state["_webhook_last_secret"]`에 `(webhook_id, secret, created_at_iso)` 저장. 동일 페이지 리렌더 동안 노출 후 사용자가 "비밀키 확인 완료" 버튼을 누르면 클리어. 다른 페이지로 이동 시 자동 소실(별도 정리 불필요 — Streamlit session_state는 페이지 간 공유되지만 이 키는 한 번 클리어되면 끝).

⚠️ secret은 절대 로그/캐시/`st.cache_data` 대상이 아님.

## 8. Tests

### 8.1 `test_webhook_admin_ui.py` 구조

```python
class _Recorder:
    """MockTransport handler: 호출 캡처 + 시나리오별 응답."""

def _client_with(*handlers) -> WebhookAdminClient: ...

def test_list_webhooks_active_filter(): ...
def test_get_webhook_404_raises(): ...
def test_create_webhook_returns_secret(): ...
def test_update_webhook_partial_patch(): ...
def test_delete_webhook_no_body(): ...
def test_test_webhook_with_payload(): ...
def test_list_deliveries_status_filter(): ...
def test_list_event_types(): ...
def test_queue_stats(): ...
def test_retry_delivery(): ...
def test_4xx_raises_webhook_admin_error_with_detail(): ...
def test_timeout_raises_with_status_none(): ...

# Formatters
def test_format_queue_stats_cards_order_and_count(): ...
def test_format_webhook_row_truncates_long_url(): ...
def test_format_delivery_row_status_emoji(): ...
def test_truncate_short_input_unchanged(): ...
def test_truncate_uses_single_ellipsis(): ...
def test_parse_event_types_dedup_and_strip(): ...
```

총 ≥ 16 테스트 (api_client 10+, formatters 6).

### 8.2 Page-level smoke

Streamlit page는 직접 import 시 `st.set_page_config` 호출로 실패 가능 → 별도 smoke 없이 AC1은 `app.py`의 nav 등록 확인 (`assert "운영" in pages`)으로 검증.

## 9. Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| `/test` 동기 호출 5s 블록 | `st.spinner("발송 중…")` 표시, timeout 6s로 client 설정 |
| event_catalog 매 rerun 재호출 | `st.cache_resource(ttl=60)` |
| 잘못된 url 입력 시 422 | 백엔드 ValidationError → 400 detail을 토스트 표시 (기존 백엔드 검증 재사용) |
| secret 노출 후 새로고침 시 분실 | session_state 키 + 사용자 명시 확인 버튼 |
| API 미가용 (서비스 다운) | 모든 view 함수가 WebhookAdminError catch → 페이지 자체는 살아있음, 빈 표 + 에러 토스트 |

## 10. Out of Scope (재확인)

- 일괄 재시도, payload 본문 모달, secret 회전 스케줄, 인증, SSE 푸시, Prometheus exporter
- 위 항목들은 별도 사이클로 분리 (`webhook-admin-ui-v2` / `webhook-metrics-v1` 등)
