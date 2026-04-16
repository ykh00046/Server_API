# Gap Analysis: gemini-fallback

> Design: [gemini-fallback.design.md](../02-design/features/gemini-fallback.design.md)

## 분석 개요

| 항목 | 값 |
|------|-----|
| Feature | gemini-fallback |
| 분석 날짜 | 2026-04-17 |
| 종합 일치율 | **98%** |

## 카테고리별 점수

| 카테고리 | 점수 | 상태 |
|----------|:-----:|:------:|
| 설계 일치도 | 97% | PASS |
| 아키텍처 준수 | 100% | PASS |
| 테스트 커버리지 | 100% | PASS |

## 항목별 비교 결과

### 1. shared/config.py (100%)

| 설계 항목 | 구현 | 일치 |
|-----------|------|:----:|
| `GEMINI_FALLBACK_MODEL` env 기본값 `gemini-3.1-flash-lite` | L54: 동일 | PASS |
| `GEMINI_FALLBACK_ENABLED` env 기본값 `true` | L55: 동일 | PASS |

### 2. api/chat.py (100%)

| 설계 항목 | 구현 | 일치 |
|-----------|------|:----:|
| `_generate_with_retry()` → `(response, model_used)` 튜플 반환 | L255, L310 | PASS |
| 기존 retry 3회 유지 | L259 | PASS |
| `FALLBACK_ENABLED` + `_is_fallbackable()` 조건 | L295 | PASS |
| `FALLBACK_STATUS_CODES = {429, 503}` | L240 | PASS |
| `ChatResponse.model_used: str` 필드 추가 | L107 | PASS |
| `chat_with_data()` 튜플 언패킹 + model_used 전달 | L340, L377-380 | PASS |
| import 확장 | L38 | PASS |

### 3. api/_chat_stream.py (99%)

| 설계 항목 | 구현 | 일치 |
|-----------|------|:----:|
| `model_to_use`, `fallback_used` 변수 | L82-83 | PASS |
| 첫 호출 실패 시 폴백 전환 | L93-120 | PASS |
| meta 이벤트: `model`, `fallback` 필드 | L123-126 | PASS |
| `_is_fallbackable()` 헬퍼 | L33-44 | PASS |
| 로그 태그 | 설계: `[Stream Fallback]` → 구현: `[ChatStream Fallback]` | INFO |

### 4. 테스트 (100%)

| 설계 케이스 | 구현 | 일치 |
|-------------|------|:----:|
| sync_fallback_on_429 | `TestSyncFallback.test_fallback_on_429` | PASS |
| sync_both_fail | `TestSyncFallback.test_both_models_fail` | PASS |
| sync_no_fallback_on_500 | `TestSyncFallback.test_no_fallback_on_500` | PASS |
| stream_fallback_on_429 | `TestStreamFallback.test_stream_fallback_on_429` | PASS |
| stream_both_fail | `TestStreamFallback.test_stream_both_fail` | PASS |
| fallback_disabled | sync + stream 양쪽 구현 (보너스) | PASS |

## 차이점

### 경미 (기능 영향 없음)

| 항목 | 설계 | 구현 | 영향 |
|------|------|------|------|
| 스트리밍 로그 태그 | `[Stream Fallback]` | `[ChatStream Fallback]` | Low — 기존 `[ChatStream ...]` 컨벤션 일관성 |
| 에러 raise 방어 | `raise last_error` | `raise last_error if last_error else RuntimeError(...)` | Low — 더 견고 |

### 누락 (RED)

없음.

## 테스트 결과

- 전체 테스트: **149개 통과** (0 실패)
- 폴백 테스트: **7개 통과** (sync 4 + stream 3)

## 결론

**Match Rate: 98% — PASS**

즉각 조치 필요한 갭 없음. 로그 태그 차이는 기존 코드 컨벤션과의 일관성을 위한 의도적 변경.
