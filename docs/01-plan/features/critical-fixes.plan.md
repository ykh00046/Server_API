# critical-fixes Planning Document

> **Summary**: 종합 검토에서 도출된 Critical 이슈 2건 — Gemini fallback 모델 안정화(C1) + AI 콘텐츠 sanitizer 단순화(C2) — 핫픽스
>
> **Project**: Server_API (Production Data Hub)
> **Version**: critical-fixes v1
> **Author**: interojo
> **Date**: 2026-04-23
> **Status**: Plan

---

## 1. Overview

### 1.1 Purpose

2026-04-23 종합 검토(`bkit:code-analyzer` + `bkit:gap-detector`)에서 도출된 Critical 이슈 중,
운영 안정성에 직접 영향을 주며 검증으로 사실 확인이 끝난 2건을 단일 사이클로 묶어 핫픽스한다.

### 1.2 Background

#### C1: Gemini Fallback 모델 안정성
- 현재 `shared/config.py:54`의 기본값은 `gemini-3.1-flash-lite` (preview 모델, 2026-03-03 출시).
- 검증 결과(WebFetch + WebSearch): Gemini Developer API의 정식 ID는 `gemini-3.1-flash-lite-preview` (`-preview` suffix 필요).
- preview 모델은 사전 통보 없이 deprecate 가능 (예: Gemini 3 Pro Preview는 2026-03-09 종료).
- Primary 모델이 `gemini-2.5-flash`(GA)인데 fallback만 unstable preview를 쓰는 비대칭 → 같은 family의 GA `gemini-2.5-flash-lite`로 정렬하는 것이 합리적.
- `tests/test_chat_fallback.py:1`의 docstring도 "3.1 Flash Lite" 가정이 박혀 있어 함께 갱신 필요.

#### C2: AI 콘텐츠 Sanitizer 단순화
- 현재 `dashboard/components/ai_section.py:146-157`의 `_UNSAFE_HTML_RE` 정규식은
  `<script>`, `on*=`, `<iframe>`, `javascript:` 등을 strip한다.
- 검증 결과: AI 응답 렌더링 지점(line 332, 454)은 `st.markdown(content)`로 호출되며,
  Streamlit 기본값 `unsafe_allow_html=False`에 의해 raw HTML은 이미 escape 처리된다.
- 즉 정규식 sanitizer는 **defense-in-depth**라기보다 **brittle한 콘텐츠 변형**에 가깝다:
  - "javascript: URL을 사용하지 마세요" 같은 정상 텍스트도 일부 strip
  - 정규식 우회는 쉬움 (HTML 엔티티, Unicode escape, `<svg onload>`)
- 따라서 **regex 제거 + `unsafe_allow_html=False` 명시화**가 더 안전하고 단순하다 (bleach 의존성 추가 불필요).

### 1.3 Related Documents

- 종합 검토 결과 (in-conversation, 2026-04-23)
- 선행 사이클: `gemini-fallback` (429/503 폴백 최초 구현, archived 2026-04)
- 선행 사이클: `sse-streaming-optimization` (AI 콘텐츠 렌더링 지점 정착, archived 2026-04)
- 메모리: `feedback_default_shadowing.md` (env 기본값 변경 시 wrapper 영향 주의)

---

## 2. Scope

### 2.1 In Scope

| ID | Item | Priority | Source | Effort |
|----|------|----------|--------|--------|
| F1 | `GEMINI_FALLBACK_MODEL` 기본값 `gemini-3.1-flash-lite` → `gemini-2.5-flash-lite` (GA) | Critical | C1 | 5min |
| F2 | `tests/test_chat_fallback.py` docstring "3.1 Flash Lite" → "2.5 Flash Lite" 갱신 | Critical | C1 | 5min |
| F3 | `dashboard/components/ai_section.py` `_UNSAFE_HTML_RE` 및 `_sanitize_ai_content()` 제거 | Critical | C2 | 10min |
| F4 | AI 응답 렌더링(line 332, 454) `st.markdown(content, unsafe_allow_html=False)` 명시 | Critical | C2 | 5min |
| F5 | `_session_store` import 등 이번 변경으로 unused가 된 항목 정리 (re/io 등) | Low | 부산물 | 5min |

### 2.2 Out of Scope

| Item | Reason |
|------|--------|
| C3 ATTACH SQL 문자열 보간 통일 | whitelist로 보호 중, 별도 사이클(`security-hardening-v3` 등)에서 다룸 |
| H1 `OFFSET {int(offset)}` 파라미터화 | offset 자체가 deprecated 표기, 제거 사이클 별도 |
| H2 `execute_custom_query` bind parameter 도입 | AI tool 입력 특성상 위험도 낮음, 별도 설계 필요 |
| H3 `_render_table_download` 파서 교체 | UX 개선 사이클로 분리 |
| 신규 모델 자동 검증 (`/healthz/ai`에서 fallback 모델까지 ping) | 후속 사이클(observability-v3) 후보 |

---

## 3. Acceptance Criteria

| AC | 내용 | 검증 방법 |
|----|------|----------|
| AC1 | `python -c "from shared.config import GEMINI_FALLBACK_MODEL; print(GEMINI_FALLBACK_MODEL)"` 결과가 `gemini-2.5-flash-lite` | shell |
| AC2 | `pytest tests/test_chat_fallback.py -q` 13개 모두 통과 (mock 기반이므로 모델명 변경 영향 없음을 확인) | pytest |
| AC3 | `dashboard/components/ai_section.py`에 `_UNSAFE_HTML_RE`, `_sanitize_ai_content` 잔존 grep 결과 0건 | grep |
| AC4 | `import re` 등 unused import가 ruff/lint에서 무경고 | python -c "import dashboard.components.ai_section" 후 ruff 또는 수동 확인 |
| AC5 | gap-detector 재실행 시 critical-fixes 사이클 일치율 ≥ 95% | bkit:gap-detector |

---

## 4. Risks

| Risk | Mitigation |
|------|-----------|
| 사용자 환경에서 `.env`로 `GEMINI_FALLBACK_MODEL`을 명시 override 했을 경우 | `.env` 우선이므로 영향 없음 (`os.getenv` 사용). README/operations_manual에 권장 모델만 명시 |
| `gemini-2.5-flash-lite`도 quota 한계 도달 가능성 | primary와 lite는 별도 quota, 실질적 분리 효과 유지 |
| AI가 Markdown 안에 의도적으로 HTML을 사용 (예: `<sup>`) | 현재도 Streamlit이 escape하므로 동작 동일 (regex 제거로 인한 변화 없음) |
| 향후 누군가 `unsafe_allow_html=True`로 변경할 경우 | 명시적 `False` 추가로 review 시 발견 용이. PR review 가이드 추가 |

---

## 5. Timeline

| Phase | Duration | Owner |
|-------|---------|-------|
| Plan + Design | 0.5h | interojo |
| Act-1: F1+F2 (config + test docstring) | 0.2h | interojo |
| Act-2: F3+F4+F5 (sanitizer 제거 + 명시화) | 0.3h | interojo |
| Check: gap-detector + smoke test | 0.3h | gap-detector |
| Report | 0.2h | report-generator |

총 예상: ~1.5h
