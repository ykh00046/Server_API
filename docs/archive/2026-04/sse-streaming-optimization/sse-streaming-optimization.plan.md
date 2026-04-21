# sse-streaming-optimization Planning Document

> **Summary**: SSE /chat/stream 스트리밍 최적화 — 청크 크기, 타임아웃, 재연결, 에러 핸들링 강화
>
> **Project**: Server_API (Production Data Hub)
> **Version**: SSE Streaming v2
> **Author**: interojo
> **Date**: 2026-04-18
> **Status**: Plan

---

## 1. Overview

### 1.1 Purpose

현재 SSE 스트리밍(`POST /chat/stream`)은 기본 기능은 안정적이나, 장시간 스트리밍 시
keepalive 부재, 클라이언트 재연결 로직 미비, 타임아웃 비대칭 등 운영 안정성 개선이 필요하다.

### 1.2 Background

- **현재 구현**: `api/_chat_stream.py` (서버 generator) + `dashboard/components/ai_section.py` (클라이언트 consumer)
- **이벤트 계약**: `meta → [tool_call]* → token+ → done` (또는 `error`)
- **알려진 이슈**:
  1. 서버: keepalive/heartbeat 없음 → 프록시/방화벽이 유휴 연결 종료 가능
  2. 클라이언트: 재연결 로직 없음 → 중단 시 부분 응답 유실
  3. 타임아웃 비대칭: 클라이언트 60s vs 서버 무제한
  4. 에러 메시지 300자 잘림 → 디버깅 어려움
  5. tool_call 동명 중복 호출 시 두 번째 이후 무시
- **테스트**: `tests/test_chat_stream.py` + `tests/test_chat_fallback.py` (총 13개)

### 1.3 Related Documents

- SSE 이벤트 계약 메모리: `project_sse_contract.md`
- 선행 사이클: `ui-modernization-streamlit-extras` (SSE 최초 구현, 97%)
- 선행 사이클: `gemini-fallback` (429/503 폴백, 98%)

---

## 2. Scope

### 2.1 In Scope

| ID | Item | Priority | Source | Effort |
|----|------|----------|--------|--------|
| S1 | 서버 Heartbeat — 청크 간 10초 초과 시 `: heartbeat\n\n` 코멘트 프레임 전송 | High | 프록시 유휴 종료 방지 | 30min |
| S2 | 서버 스트림 타임아웃 — 총 스트리밍 120초 제한 + timeout 이벤트 | High | 무한 hang 방지 | 30min |
| S3 | 클라이언트 자동 재연결 — ConnectError/ReadTimeout 시 1회 자동 재시도 (backoff 2s) | Medium | UX 안정성 | 45min |
| S4 | 청크 버퍼링 — 50ms 미만 간격 토큰을 묶어 전송 (네트워크 오버헤드 감소) | Medium | 성능 | 45min |
| S5 | 에러 핸들링 강화 — 구조화된 에러 코드 체계 + 클라이언트 에러별 한글 메시지 | Medium | 디버깅/UX | 30min |
| S6 | tool_call 중복 허용 — `tools_emitted` set 대신 카운트 기반으로 변경 | Low | 정확성 | 15min |

### 2.2 Out of Scope

| Item | Reason |
|------|--------|
| WebSocket 전환 | SSE로 충분, 양방향 통신 불필요 |
| 부분 응답 세션 저장 | 설계 의도 — 불완전 응답으로 세션 오염 방지 |
| 스트리밍 압축 (gzip) | 텍스트 청크 크기 작음, 오버헤드 > 이점 |
| 다중 동시 스트림 | 현재 사용 패턴에서 불필요 |

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01 | 청크 간 10초 초과 시 SSE 코멘트 heartbeat 자동 전송 | High |
| FR-02 | 총 스트리밍 시간 120초 초과 시 timeout 에러 이벤트 + 스트림 종료 | High |
| FR-03 | 클라이언트 ConnectError/ReadTimeout 시 2초 대기 후 1회 자동 재시도 | Medium |
| FR-04 | 50ms 미만 간격 토큰 버퍼링 후 단일 `token` 이벤트로 병합 전송 | Medium |
| FR-05 | 에러 이벤트에 구조화된 code 필드 (timeout, model_error, rate_limited, internal) | Medium |
| FR-06 | tool_call 이벤트에서 동명 함수 중복 호출 허용 (count 기반) | Low |

### 3.2 Non-Functional Requirements

| Category | Criteria |
|----------|----------|
| Latency | 첫 토큰 지연(TTFT) 현행 대비 악화 없음 |
| Compatibility | 기존 SSE 이벤트 계약 유지 (meta → token → done) |
| Backward Compat | 클라이언트가 heartbeat 코멘트를 무시하도록 (SSE 표준) |
| Test Coverage | 신규 기능당 최소 2개 테스트 추가 |
| Reliability | 30분 연속 스트리밍 세션에서 연결 유지 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] Heartbeat 코멘트 정상 전송 (10초 간격)
- [ ] 120초 타임아웃 시 `timeout` 에러 이벤트 발생
- [ ] 클라이언트 1회 재시도 후 성공 시 정상 응답 표시
- [ ] 토큰 버퍼링으로 네트워크 이벤트 수 30%+ 감소
- [ ] 에러 코드 체계 적용 (4종)
- [ ] tool_call 중복 호출 정상 전송
- [ ] 기존 13개 테스트 통과
- [ ] 신규 테스트 8개+ 추가

### 4.2 Quality Criteria

- [ ] Streamlit 서버 정상 기동
- [ ] 기존 149+ 테스트 전체 통과
- [ ] heartbeat가 클라이언트 파싱에 영향 없음
- [ ] 기존 기능 회귀 없음

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| S4: 버퍼링으로 TTFT 증가 | Medium | Medium | 첫 토큰은 즉시 전송 (버퍼 적용 안 함) |
| S1: heartbeat가 클라이언트 파싱 깨뜨림 | High | Low | SSE 표준 코멘트 (`:` 접두사) — 파서가 이미 무시 |
| S2: 정상 장문 응답이 120초 타임아웃에 걸림 | Medium | Low | 타임아웃을 config에서 조절 가능하게 |
| S3: 재시도 시 중복 요금 (Gemini API) | Low | Medium | 1회 제한, 재시도 전 사용자 알림 없이 투명 처리 |
| S5: 에러 코드 변경으로 기존 테스트 깨짐 | Medium | Medium | 하위 호환 — `message` 필드 유지, `code` 필드 추가 |

---

## 6. Architecture Considerations

### 6.1 Project Level

Dynamic (기존 유지)

### 6.2 Key Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| Heartbeat 방식 | SSE 코멘트 / 빈 data / ping 이벤트 | SSE 코멘트 (`: heartbeat`) | SSE 표준, 클라이언트 파서 자동 무시 |
| 타임아웃 위치 | asyncio.wait_for / 수동 시간 체크 | asyncio 기반 chunk timeout + 총 시간 | asyncio.timeout (Python 3.11+) |
| 버퍼링 방식 | time-based / size-based / hybrid | time-based (50ms) | 일정 간격 flush가 UX에 자연스러움 |
| 재연결 전략 | 자동 무한 / 1회 / 수동 | 1회 자동 (2s backoff) | 무한 재시도는 과금 위험 |
| 에러 코드 체계 | HTTP status / 커스텀 string / enum | 커스텀 string (4종) | SSE 내부 이벤트이므로 HTTP status 부적합 |

### 6.3 Implementation Order

```
1. S5: 에러 코드 체계 (기반 작업, 다른 항목에서 참조)
2. S6: tool_call 중복 허용 (단순, 리스크 최소)
3. S1: 서버 heartbeat (핵심, 독립적)
4. S2: 서버 스트림 타임아웃 (S1과 함께 동작)
5. S4: 청크 버퍼링 (S1/S2 위에 구축)
6. S3: 클라이언트 재연결 (모든 서버 변경 반영 후)
```

---

## 7. File Change Summary

| 구분 | 파일 | 변경 내용 |
|------|------|----------|
| MOD | `api/_chat_stream.py` | S1: heartbeat, S2: timeout, S4: 버퍼링, S5: 에러 코드, S6: tool_call |
| MOD | `dashboard/components/ai_section.py` | S3: 재연결, S5: 에러 메시지 한글화 |
| MOD | `shared/config.py` | S1/S2: STREAM_HEARTBEAT_SEC, STREAM_TIMEOUT_SEC 설정 추가 |
| MOD | `tests/test_chat_stream.py` | S1-S6: 신규 테스트 추가 |
| NEW | `tests/test_stream_resilience.py` | S3: 클라이언트 재연결 테스트 (선택) |

---

## 8. Next Steps

1. [ ] Design document (`/pdca design sse-streaming-optimization`)
2. [ ] Implementation
3. [ ] Gap Analysis
4. [ ] Completion Report
5. [ ] Archive

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-04-18 | Initial plan — SSE 최적화 6건 정리 | interojo |
