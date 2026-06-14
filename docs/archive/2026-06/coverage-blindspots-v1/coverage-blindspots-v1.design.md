# coverage-blindspots-v1 — Design

> **Cycle**: coverage-blindspots-v1
> **PDCA Phase**: Design
> **Date**: 2026-06-14
> **Plan**: [[coverage-blindspots-v1.plan]]

## 0. 설계 원칙

1. **추출만, 로직 변경 0** — 두 파서의 휴리스틱을 한 글자도 바꾸지 않고 순수 함수로 옮긴다. 테스트는 characterization(현재 동작 고정).
2. **streamlit-free 모듈** — 파서는 `io`/`json`/`pandas`만 의존하는 신규 `dashboard/components/_parsing.py`. UI 함수(`ai_section.py`)는 이 헬퍼를 호출만.
3. **테스트는 격리 import** — `test_webhook_admin_ui.py:19`의 선례대로 `importlib.util`로 `_parsing.py`만 로드(패키지 `__init__`/streamlit 회피). 파서가 streamlit-free라 가능.

## 1. Track A — 죽은 코드 삭제

- 삭제: `shared/utils/data_helpers.py`, `shared/utils/date_helpers.py`.
- `shared/utils/__init__.py`(빈 파일): `shared/utils/` 아래 다른 파일 없으면 디렉터리째 삭제. (Do에서 잔존 파일 확인)
- **삭제 직전 재검증**: `data_helpers|date_helpers|format_large_number|to_korean_category|resolve_display_unit|get_current_week_range|calculate_change_percentage|parse_production_date` 전수 grep(동적/문자열 참조 포함) 0건 확인 → 삭제.
- 효과: measured coverage 분모에서 91 stmt(0%) 제거 → % 상승. before/after 실측 기록(AC2).

## 2. Track B — 파서 추출 (`dashboard/components/_parsing.py` 신규)

### 2.1 마크다운 표 파서 (현 `_render_table_download` 147-163 그대로 이전)

```python
import io, json
from collections.abc import Iterable, Iterator
import pandas as pd

def parse_markdown_table(content: str) -> pd.DataFrame | None:
    """Extract the first markdown table in `content` as a DataFrame, or None.
    Pure port of the original _render_table_download heuristics — behavior
    must not change (characterization-tested)."""
    if "|" not in content or "\n|" not in content:
        return None
    lines = content.split("\n")
    table_lines = [
        line for line in lines if "|" in line and line.strip().startswith("|")
    ]
    if len(table_lines) <= 2:
        return None
    table_text = "\n".join(table_lines).replace("**", "")
    try:
        df = pd.read_csv(
            io.StringIO(table_text.replace(" ", "")), sep="|"
        ).dropna(how="all", axis=1)
        df = df[~df.iloc[:, 0].str.contains(r"^-+$", na=False)]
        df.columns = [col.strip() for col in df.columns]
    except Exception:  # noqa: BLE001 — 파싱 실패는 "표 없음"으로 취급(원동작 보존)
        return None
    if df.empty:
        return None
    return df
```

### 2.2 SSE 이벤트 파서 (현 `_stream_chat_tokens_once` 89-102의 와이어 파싱부)

```python
def parse_sse_events(lines: Iterable[str]) -> Iterator[tuple[str | None, dict]]:
    """Yield (event_name, data) per valid SSE `data:` line. Pure: no I/O, no
    streamlit. Blank line resets event name; malformed JSON is skipped.
    The caller decides per-event behavior (token/tool_call/error/done)."""
    event_name: str | None = None
    for line in lines:
        if not line:
            event_name = None
            continue
        if line.startswith("event:"):
            event_name = line[6:].strip()
            continue
        if line.startswith("data:"):
            raw = line[5:].strip()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            yield event_name, data
```

### 2.3 호출부 교체 (`ai_section.py`)

- `_render_table_download`: 파싱부 → `df = parse_markdown_table(content); if df is None: return`. 이후 ExcelWriter+download_button(+자체 try/except) 유지. **동작 동일**(원래도 파싱 throw → 전체 silent return).
- `_stream_chat_tokens_once`: `for event_name, data in parse_sse_events(r.iter_lines()):` 루프로 교체, 각 분기의 `st.toast`/`st.error`/`session_state`/`yield`는 그대로. status!=200 가드와 httpx.stream 컨텍스트는 UI 함수에 잔존.
- import: `from ._parsing import parse_markdown_table, parse_sse_events`.

## 3. 테스트

### 3.1 `tests/test_ai_table_parse.py` (≥6, AC5)
`_parsing.py`를 importlib로 격리 로드. 케이스:
1. 정상 3열 표 → DataFrame(행/열 수·값 검증)
2. 표 없음(`|` 무) → None
3. 헤더+구분선만(table_lines ≤ 2) → None
4. `**굵게**` 포함 셀 → `**` 제거되어 파싱
5. 공백 포함 셀 → 공백 제거 동작(characterization: 현재는 셀 내부 공백도 제거됨 — 그대로 고정 + 주석으로 알려진 한계 명시)
6. 구분선 행(`---`) 필터링 확인
7. (보너스) 파싱 불가 → None

### 3.2 `tests/test_sse_parse.py` (≥5, AC5)
1. token 다건 → (None/“token”, {text}) 순서·텍스트
2. event+data 정상쌍, blank line이 event 리셋
3. 깨진 JSON data 라인 → 스킵(예외 없음)
4. error/done 이벤트 → 해당 (name, data) 산출(소비자 분기는 UI 책임이므로 파서는 튜플만)
5. `data:` 없는 event-only → 산출 없음
6. (보너스) 멀티 이벤트 혼합 순서 보존

## 4. 커밋 계층

| # | 커밋 | 내용 |
|---|------|------|
| 1 | `chore(shared): 미사용 utils(data/date_helpers) 삭제` | Track A |
| 2 | `refactor(dashboard): AI 표/SSE 파서를 streamlit-free _parsing.py로 추출 + 테스트` | Track B |
| 3 | `docs(pdca): ...` | 문서 |

## 5. AC 매핑
AC1·AC2→§1 / AC3→§2.1+§2.3 / AC4→§2.2+§2.3 / AC5→§3 / AC6→게이트+CI / AC7→추출 전후 동작 보존(테스트가 캡처) / AC8→Check.
