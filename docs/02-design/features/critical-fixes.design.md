# critical-fixes Design Document

> **Summary**: Cycle 1 핫픽스 — 모델명 정렬(C1) + sanitizer 단순화(C2) 구현 설계
>
> **Project**: Server_API (Production Data Hub)
> **Version**: critical-fixes v1
> **Author**: interojo
> **Date**: 2026-04-23
> **Status**: Design

---

## 1. Architecture Decisions

### AD-1: Fallback 모델은 primary와 같은 family의 GA 사용

**선택지 비교**

| 옵션 | 안정성 | preview 위험 | 비용 | 결정 |
|------|--------|------------|------|------|
| A. `gemini-3.1-flash-lite-preview` (preview suffix 추가) | 중 | preview deprecate 가능 | 동일 | ✗ |
| B. `gemini-2.5-flash-lite` (GA, primary와 같은 family) | **고** | 없음 | 동일 | **✓** |
| C. `gemini-3.1-flash-lite` (현재 잘못된 ID) | 저 | 호출 실패 가능 | - | ✗ |

**선택 근거**: B
- Preview 모델은 사전 통보 없이 종료 가능 (선례: Gemini 3 Pro Preview, 2026-03-09 shutdown).
- Primary `gemini-2.5-flash`와 동일 family로 동작 일관성 확보 (tool calling, system instruction format 등).
- env override(`GEMINI_FALLBACK_MODEL`)로 사용자가 preview를 선택하고 싶으면 자유 선택 가능.

### AD-2: AI 콘텐츠 sanitizer는 제거하고 Streamlit 기본 동작에 위임

**선택지 비교**

| 옵션 | 보안 강도 | 의존성 추가 | 콘텐츠 왜곡 위험 | 결정 |
|------|---------|-----------|---------------|------|
| A. bleach 화이트리스트 sanitize | 고 | bleach 추가 | 낮음 | ✗ (over-engineering) |
| B. regex sanitizer 유지 | 저 (우회 가능) | 없음 | **있음** ("javascript:" 텍스트 strip 등) | ✗ |
| C. regex 제거 + `unsafe_allow_html=False` 명시 | 중-고 (Streamlit 기본 escape) | 없음 | 없음 | **✓** |

**선택 근거**: C
- Streamlit `st.markdown()`은 `unsafe_allow_html=False`(기본값)일 때 raw HTML을 escape한다 ([Streamlit docs](https://docs.streamlit.io/develop/api-reference/text/st.markdown)).
- 따라서 AI가 `<script>...</script>`를 출력해도 실행되지 않고 escaped 텍스트로 표시된다.
- regex 제거는 brittle한 콘텐츠 왜곡(정상 코드 예시 strip 등)을 없애는 동시에 보안 등가성을 유지한다.
- `False` 명시는 "이 호출은 의도적으로 HTML을 escape한다"는 review hint 역할.

---

## 2. File-Level Changes

### 2.1 `shared/config.py`

```diff
- GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.1-flash-lite")
+ GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash-lite")
```

### 2.2 `tests/test_chat_fallback.py`

Module docstring (line 2): "(3.1 Flash Lite)" → "(2.5 Flash Lite, primary와 같은 family)" 정렬.
테스트 자체는 mock 기반이라 모델명 변경 영향 없음 (검증 항목: monkeypatch로 GEMINI_FALLBACK_ENABLED, MAX_RETRIES만 조작).

### 2.3 `dashboard/components/ai_section.py`

#### 2.3.1 제거 항목

- L13 `import re` (다른 곳에서 사용 없으므로 제거)
- L146-152 `_UNSAFE_HTML_RE` 상수 정의
- L155-157 `_sanitize_ai_content()` 함수 정의

#### 2.3.2 호출부 변경

```diff
  with st.chat_message(message["role"], avatar=avatar):
-     content = _sanitize_ai_content(message["content"])
-     st.markdown(content)
+     content = message["content"]
+     st.markdown(content, unsafe_allow_html=False)
      if message["role"] == "assistant":
          _render_table_download(content, "dl_ai_table", i)
```

동일 패턴 2곳:
- `render_ai_chat()` 내부 (line 328-332)
- `render_ai_section_compact()` 내부 (line 449-454)

#### 2.3.3 `_render_table_download()`는 변경 없음

`_render_table_download()`는 markdown 표를 파싱해 Excel 다운로드 버튼을 만드는 로직으로,
sanitize와 무관. 입력값은 변경 없는 raw content 그대로 전달.

---

## 3. Test Plan

### 3.1 단위 검증

| Test | 명령 | 기대 |
|------|------|------|
| Config 기본값 | `python -c "from shared.config import GEMINI_FALLBACK_MODEL; print(GEMINI_FALLBACK_MODEL)"` | `gemini-2.5-flash-lite` |
| Fallback 테스트 회귀 | `pytest tests/test_chat_fallback.py -q` | 13 passed |
| Import 무경고 | `python -c "import dashboard.components.ai_section as m; print('ok')"` | `ok` |
| Sanitizer 잔존 검사 | `grep -RIn '_sanitize_ai_content\|_UNSAFE_HTML_RE' dashboard api shared tests` | 결과 0건 |

### 3.2 수동 smoke 검증 (선택)

- 대시보드 실행 후 AI 채팅에 다음 query: `<script>alert(1)</script> 라는 문자열을 그대로 다시 출력해줘`
  → 응답에 `<script>` 태그가 escape되어 텍스트로 표시되는지 확인 (alert 실행되지 않음).

---

## 4. Rollback Strategy

각 commit은 단일 layer 변경(메모리 `feedback_commit_style.md` 정책 준수)이므로,
문제가 발생하면 해당 commit만 `git revert`하면 즉시 원복된다.

| Commit 단위 | Revert 영향 |
|-----------|-----------|
| C1 (config + test docstring) | fallback 모델만 원복, primary는 영향 없음 |
| C2 (sanitizer 제거 + 명시화) | regex sanitizer 복귀, 다른 동작 영향 없음 |

---

## 5. Open Questions

- (해결됨) C1 모델명 정확성 → WebFetch로 검증 완료. `gemini-3.1-flash-lite`는 실존하나 preview, 안정성을 위해 GA `gemini-2.5-flash-lite` 선택.
- (해결됨) C2 bleach 필요성 → Streamlit 기본 escape로 충분, 의존성 추가 불필요.
- (deferred) `/healthz/ai`에서 fallback 모델까지 ping 검증 → 후속 사이클 (`observability-v3` 후보).
