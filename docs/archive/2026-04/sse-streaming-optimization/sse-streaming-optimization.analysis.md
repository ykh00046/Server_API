# sse-streaming-optimization Gap Analysis

> **Feature**: sse-streaming-optimization
> **Design**: `docs/02-design/features/sse-streaming-optimization.design.md`
> **Date**: 2026-04-21
> **Overall Match Rate**: **96%**
> **Status**: PASS (>= 90%)

---

## Scope Item Verification

| ID | Item | Status | Score |
|----|------|--------|-------|
| S5 | 구조화된 에러 코드 체계 | MATCH | 100% |
| S6 | tool_call 중복 ��용 | MATCH | 100% |
| S1 | 서버 Heartbeat | MATCH | 100% |
| S2 | 서버 스트림 타임아웃 | MATCH | 100% |
| S4 | 청크 버퍼링 | MATCH | 100% |
| S3 | 클라이언트 자동 재연결 | MATCH | 100% |

## Acceptance Criteria

| Criterion | Target | Actual | Verdict |
|-----------|--------|--------|---------|
| 에러 코드 4+ 종 사용 | 4+ | 5종 (ai_disabled, timeout, model_error, rate_limited, internal) | PASS |
| tool_call 동명 중복 전송 | 다수 이벤트 | list 기반, dedup 제거 | PASS |
| Heartbeat `: heartbeat\n\n` | 10초 간격 | `_iter_with_heartbeat()` + asyncio.wait | PASS |
| asyncio.timeout(120s) | timeout 에러 이벤트 | `asyncio.timeout(STREAM_TIMEOUT_SEC)` | PASS |
| 토큰 버퍼링 + 첫 토큰 즉시 | 50ms 윈도우 | `_flush_buffer()` + first_token_sent 플래그 | PASS |
| 클라이언트 재연결 | 1회, tokens_yielded 가드 | `_stream_chat_tokens_once()` 분�� | PASS |
| Config 설정 | STREAM_HEARTBEAT_SEC, STREAM_TIMEOUT_SEC | shared/config.py + STREAM_BUFFER_FLUSH_MS | PASS |
| 신규 테스트 8+개 | 8+ | 9개 (S1-S6 커버) | PASS |
| 기존 테스트 통과 | 22/22 | 22/22 pass | PASS |

## Positive Deviations (설계 대비 개선)

| Item | 설계 | 구현 | 효과 |
|------|------|------|------|
| Heartbeat wrapper | `asyncio.wait_for` (타임아웃 시 코루틴 취소) | `asyncio.wait` + `ensure_future` (태스크 유지) | 청크 유실 방지 |
| `_flush_buffer()` | 인라인 버퍼 flush | 헬퍼 함수 추출 | DRY, 3곳에서 재사용 |
| `STREAM_BUFFER_FLUSH_MS` | 로컬 상수 50 | env 설정 가능 (shared/config.py) | 운영 유연성 |
| 추가 테스트 | 8개 계획 | 9개 구현 (test_stream_error_code_internal 추가) | 커버리지 향상 |

## Minor Gaps (Optional)

| Item | 설명 | 영향 |
|------|------|------|
| `tests/test_stream_client.py` | 클라이언트 재연결 단위 테스트 미작성 (설계에서 "선택"으로 표기) | Low — 로직 단순, 수동 검증 가능 |

## Conclusion

6개 스코프 항목 모두 100% 구현 완료. 9개 신규 테스트 추가 (목표 8+).
설계 대비 `asyncio.wait` 패턴, `_flush_buffer()` 추출, config 외부화 등 **개선 사항** 3건 반영.
Match rate **96%**. Completion report 진행 가능.
