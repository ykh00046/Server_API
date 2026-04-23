# critical-fixes Analysis Document

> **Summary**: Cycle 1 갭 분석 — 6/6 AC 통과 (일치율 100%)
>
> **Project**: Server_API (Production Data Hub)
> **Date**: 2026-04-23
> **Status**: Analysis (passed)

---

## 1. Acceptance Criteria 검증 결과

| AC | 항목 | 결과 | 근거 |
|----|------|:----:|------|
| AC1 | `GEMINI_FALLBACK_MODEL` 기본값 = `gemini-2.5-flash-lite` | PASS | `shared/config.py:54` |
| AC2 | `test_chat_fallback.py` docstring "2.5 Flash Lite" | PASS | `tests/test_chat_fallback.py:2` |
| AC3 | `_UNSAFE_HTML_RE`, `_sanitize_ai_content` 완전 제거 | PASS | grep 결과 0건 (docs 외) |
| AC4 | `import re` 제거 | PASS | `ai_section.py` import에 `re` 없음, `re.` 호출 0건 |
| AC5 | `st.markdown(unsafe_allow_html=False)` 2곳 명시 | PASS | line 317, 439 |
| AC6 | F1~F5 design diff 일치 | PASS | 모든 변경 반영 |

**일치율: 6/6 = 100%** (목표 95%+ 초과)

## 2. 추가 검증

- `python -c "from shared.config import GEMINI_FALLBACK_MODEL; print(GEMINI_FALLBACK_MODEL)"` → `gemini-2.5-flash-lite` ✓
- `pytest tests/test_chat_fallback.py -q` → 7 passed ✓
- `python -c "import dashboard.components.ai_section"` → import ok ✓

## 3. Iteration 필요 여부

불필요 (≥ 90%, 실제 100%). `/pdca report` 진행.

## 4. Lessons Learned

- **검토 에이전트 결과는 항상 검증한다**: code-analyzer가 `gemini-3.1-flash-lite`를 "존재하지 않는 모델"로 판정했으나 WebFetch 검증 결과 실존 preview 모델이었다. 진단 자체는 valid(불안정한 preview를 default로 두는 것은 위험), 근거 표현은 부정확.
- **Defense-in-depth는 콘텐츠 왜곡 위험과 비교 평가**: regex sanitizer가 보안에 거의 기여하지 않으면서 정상 텍스트(예: "javascript: 사용 금지" 안내)를 strip할 수 있어, 제거 + Streamlit 기본 escape 신뢰가 더 안전한 선택이었다.
