# Plan: SQL Validation Tests + Multi-turn AI Chat

> PDCA Phase: **Plan**
> Feature: `sql-tests-and-multiturn-chat`
> Created: 2026-02-13
> Status: Draft

---

## 1. Background & Motivation

### T1: SQL 검증 단위 테스트
PDCA #1(4-critical-issues-fix)에서 `execute_custom_query`의 SQL Injection 방어 로직을 강화했으나,
자동화된 테스트가 없어 회귀 검증이 불가능한 상태입니다.

- `_strip_sql_comments()` — 주석 제거 로직
- 세미콜론 차단, SELECT 검증, 13개 금지 키워드, 테이블 참조 검증
- 이 5단계 검증 파이프라인에 대한 엣지케이스 테스트가 필요

### M1: Multi-turn AI 대화
현재 AI 채팅(`api/chat.py`)은 **단일 턴** 방식:
- 매 요청마다 `contents=request.query` (문자열 하나)만 전달
- 이전 대화 맥락 없음 → "방금 말한 제품의 월별 추이는?" 같은 후속 질문 불가
- 사용자 경험 저하

---

## 2. Goals

| ID | 목표 | 측정 기준 |
|:--:|------|----------|
| G1 | SQL 검증 로직 100% 엣지케이스 커버 | pytest 통과율 100%, 12+ 테스트 케이스 |
| G2 | 이전 대화 맥락 유지 | 후속 질문이 이전 도구 결과를 참조하여 답변 |
| G3 | 세션 메모리 자동 정리 | TTL 만료 시 자동 삭제, 메모리 누수 없음 |

---

## 3. Scope

### In Scope

| ID | 항목 | 파일 | 난이도 |
|:--:|------|------|:------:|
| T1 | SQL 검증 pytest | `tests/test_sql_validation.py` (신규) | Low |
| M1 | Multi-turn 세션 저장소 | `api/chat.py` | Medium |
| M2 | ChatRequest에 session_id 추가 | `api/chat.py` | Low |
| M3 | 대화 이력을 Gemini contents에 전달 | `api/chat.py` | Medium |

### Out of Scope

- 데이터베이스 연동 테스트 (DB 파일 필요 — 순수 검증 로직만 테스트)
- 프론트엔드 채팅 UI 변경 (API 레벨만)
- 무한 대화 이력 (최대 턴 수 제한)

---

## 4. Detailed Plan

### T1. SQL 검증 단위 테스트

**신규 파일:** `tests/test_sql_validation.py`

**테스트 대상 함수:**
- `_strip_sql_comments(sql)` — 주석 제거
- `execute_custom_query(sql)` — 5단계 검증 파이프라인 (검증 부분만, DB 실행 전까지)

**테스트 케이스:**

| # | 카테고리 | 입력 | 예상 결과 |
|:-:|---------|------|----------|
| 1 | 주석 제거 | `/* comment */ SELECT ...` | 주석 제거됨 |
| 2 | 주석 제거 | `SELECT -- comment\n* FROM ...` | 라인 주석 제거됨 |
| 3 | 세미콜론 | `SELECT 1; DROP TABLE x` | error: semicolon |
| 4 | 세미콜론+주석 | `SELECT /* ; */ 1 FROM production_records` | 주석 안 세미콜론은 제거됨, 통과 |
| 5 | SELECT 검증 | `DELETE FROM production_records` | error: SELECT only |
| 6 | SELECT 우회 | `/* */ DELETE FROM production_records` | error: SELECT only (주석 제거 후) |
| 7 | 금지 키워드 | `SELECT * FROM production_records; DROP TABLE` | error: semicolon (먼저 차단) |
| 8 | PRAGMA 차단 | `SELECT 1 FROM production_records WHERE PRAGMA` | error: PRAGMA |
| 9 | ATTACH 차단 | `SELECT 1 FROM production_records WHERE ATTACH` | error: ATTACH |
| 10 | 테이블 참조 | `SELECT 1 FROM users` | error: must reference production_records |
| 11 | 정상 쿼리 | `SELECT * FROM production_records LIMIT 10` | 검증 통과 (DB 없어도 검증 단계까지) |
| 12 | LIMIT 자동 추가 | `SELECT * FROM production_records` | LIMIT 1000 자동 추가 |

### M1-M3. Multi-turn AI 대화

**ChatRequest 변경:**
```python
class ChatRequest(BaseModel):
    query: str
    session_id: str | None = None  # 없으면 단일 턴
```

**세션 저장소:**
- 인메모리 dict: `{session_id: {"history": [...], "last_access": timestamp}}`
- TTL: 30분 (마지막 접근 기준)
- 최대 이력: 10턴 (초과 시 오래된 턴 삭제)
- 주기적 정리: 요청마다 만료 세션 삭제 (lazy cleanup)

**Gemini contents 전달 변경:**
- 현재: `contents=request.query` (문자열)
- 변경: `contents=[...history, user_message]` (Content 리스트)
- Gemini의 `automatic_function_calling_history`에서 도구 호출/응답도 이력에 포함

---

## 5. Modified Files Summary

| 파일 | 변경 유형 | 항목 |
|------|----------|------|
| `tests/test_sql_validation.py` | 신규 생성 | T1: pytest 12+ 케이스 |
| `api/chat.py` | Modified | M1-M3: 세션 저장소, ChatRequest, contents 변경 |

---

## 6. Verification Plan

1. **T1 검증:** `pytest tests/test_sql_validation.py -v` → 전체 통과
2. **M1 검증:** session_id로 후속 질문 → 이전 맥락 참조 응답
3. **M2 검증:** session_id 없이 요청 → 기존 단일 턴 동작 유지 (하위 호환)
4. **M3 검증:** 30분 비활성 세션 → 자동 정리 확인
