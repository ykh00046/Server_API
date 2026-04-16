# Plan: Gemini Model Fallback (Flash → 3.1 Flash Lite)

## 1. 개요

| 항목 | 내용 |
|------|------|
| Feature | gemini-fallback |
| 목표 | Gemini 2.5 Flash 실패 시 3.1 Flash Lite 자동 폴백으로 서비스 가용성 확보 |
| 배경 | 무료 티어 Flash RPM 5/RPD 20 한도로 429/503 에러 빈발 |
| 폴백 모델 | `gemini-3.1-flash-lite` — RPM 15 / RPD **500** (Flash 대비 25배) |
| 영향 범위 | `api/` — chat.py, _chat_stream.py, shared/config.py |

## 2. 무료 모델 현황 (2026-04 기준)

| 모델 | RPM | TPM | RPD |
|------|-----|-----|-----|
| Gemini 2.5 Flash (기본) | 5 | 250K | 20 |
| Gemini 2.5 Flash Lite | 10 | 250K | 20 |
| Gemini 3 Flash | 5 | 250K | 20 |
| **Gemini 3.1 Flash Lite (폴백)** | **15** | **250K** | **500** |

> 3.1 Flash Lite만 RPD 500으로 압도적. 폴백 대상으로 최적.

## 3. 현재 문제

- `gemini-2.5-flash` 단일 모델 사용, 폴백 없음
- 무료 티어 한도: RPM 5 / RPD 20 → 하루 20회 초과 시 서비스 불가
- `_generate_with_retry()`는 **같은 모델**로만 3회 재시도 (429/500/503)
- `_chat_stream.py`는 재시도 로직 자체가 없음 — 1회 실패 시 즉시 에러 이벤트

## 4. 목표 동작

```
요청 → 2.5 Flash 호출
         ├─ 성공 → 응답 반환
         └─ 429/503 실패 (retry 소진) → 3.1 Flash Lite 폴백 1회
                                          ├─ 성공 → 응답 반환 (fallback=true 표시)
                                          └─ 실패 → 에러 반환
```

## 5. 변경 계획

### 5.1 `shared/config.py`
- `GEMINI_FALLBACK_MODEL` 환경변수 추가 (기본값: `gemini-3.1-flash-lite`)
- `GEMINI_FALLBACK_ENABLED` 환경변수 추가 (기본값: `true`)

### 4.2 `api/chat.py` — sync 엔드포인트
- `_generate_with_retry()` 수정: retry 3회 소진 후 fallback 모델로 1회 추가 시도
- 폴백 사용 시 로그에 `[Fallback]` 태그 기록
- `ChatResponse`에 `model_used: str` 필드 추가 (어떤 모델이 응답했는지)

### 4.3 `api/_chat_stream.py` — SSE 스트리밍 엔드포인트
- `run_stream()` 에서 첫 호출 실패 시 fallback 모델로 재시도
- `meta` 이벤트에 `fallback: true`, `model` 필드 반영
- SSE 이벤트 순서 유지: `meta → [tool_call]* → token+ → done`

### 4.4 테스트
- `tests/test_chat_stream.py` — fallback 시나리오 테스트 추가
- Flash 실패 → Flash-Lite 성공 케이스
- 양쪽 모두 실패 케이스

## 5. 변경하지 않는 것

- `_gemini_client.py` — 클라이언트는 단일 인스턴스 유지 (모델은 호출 시 지정)
- SSE 이벤트 프로토콜 — 기존 순서/구조 변경 없음
- `_tool_dispatch.py` — tool 목록은 모델과 무관
- rate_limiter — 서버 측 rate limit은 모델별 분리 불필요

## 6. 위험 요소

| 위험 | 대응 |
|------|------|
| 3.1 Flash Lite 품질 차이 (tool calling 정확도) | 폴백임을 UI에 표시, 로그 모니터링 |
| 3.1 Flash Lite도 한도 소진 | RPD 500이므로 사실상 무료 티어 내 충분, 부족 시 유료 전환 |
| 폴백 시 응답 지연 | retry 3회 + fallback 1회 = 최대 ~20초, MAX_TOTAL_DELAY 내 관리 |

## 7. 완료 기준

- [ ] Flash 429/503 시 Flash-Lite 자동 전환 동작
- [ ] sync/stream 양쪽 엔드포인트 모두 폴백 지원
- [ ] 응답에 사용된 모델 정보 포함
- [ ] 폴백 on/off 환경변수 제어 가능
- [ ] 기존 테스트 통과 + 폴백 테스트 추가
